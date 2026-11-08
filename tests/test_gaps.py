from datetime import datetime, timedelta

from boya_kit.gaps import (
    course_assessment_outcome,
    gaps_payload,
    needed_categories,
    parse_gaps,
    requirements_met,
    selection_requirements_met,
)


def sample_statistics() -> dict:
    return {
        "validCount": 2,
        "statistical": {
            "group": {
                "1|德育": {
                    "assessmentCount": "2",
                    "selectAssessmentCount": "1",
                    "completeAssessmentCount": "1",
                    "failAssessmentCount": "0",
                    "undoneAssessmentCount": "1",
                },
                "2|美育": {
                    "assessmentCount": "1",
                    "selectAssessmentCount": "1",
                    "completeAssessmentCount": "0",
                    "failAssessmentCount": "1",
                    "undoneAssessmentCount": "0",
                },
            }
        },
    }


def test_parse_gaps() -> None:
    gaps = parse_gaps(sample_statistics())
    assert [gap.category for gap in gaps] == ["德育", "美育"]
    assert gaps[0].needs_more
    assert gaps[0].remaining_to_select == 1
    assert gaps[0].pending == 0
    assert gaps[1].valid_selected == 0
    assert gaps[1].needs_more is True
    assert gaps[1].remaining_to_select == 1
    assert gaps[1].remaining_to_pass == 1


def test_needed_categories() -> None:
    assert needed_categories(sample_statistics()) == ["德育", "美育"]
    assert not requirements_met(sample_statistics())
    assert not selection_requirements_met(sample_statistics())
    assert not selection_requirements_met(
        sample_statistics(),
        exclude={"德育"},
    )
    assert selection_requirements_met(
        sample_statistics(),
        exclude={"德育", "美育"},
    )


def test_failed_course_requires_a_replacement_selection() -> None:
    stats = {
        "statistical": {
            "group": {
                "55|德育": {
                    "assessmentCount": "2",
                    "selectAssessmentCount": "2",
                    "completeAssessmentCount": "1",
                    "failAssessmentCount": "1",
                    "undoneAssessmentCount": "1",
                }
            }
        }
    }
    gaps = parse_gaps(stats)
    assert gaps[0].selected == 2
    assert gaps[0].valid_selected == 1
    assert gaps[0].remaining_to_select == 1
    assert needed_categories(stats) == ["德育"]
    assert not selection_requirements_met(stats)


def test_unselected_slots_are_required_even_when_undone_count_is_zero() -> None:
    stats = {
        "statistical": {
            "group": {
                "57|劳动教育": {
                    "assessmentCount": "2",
                    "selectAssessmentCount": "0",
                    "completeAssessmentCount": "0",
                    "failAssessmentCount": "0",
                    "undoneAssessmentCount": "0",
                }
            }
        }
    }
    gaps = parse_gaps(stats)
    assert gaps[0].remaining_to_select == 2
    assert needed_categories(stats) == ["劳动教育"]
    assert not requirements_met(stats)
    assert not selection_requirements_met(stats)
    payload = gaps_payload(stats)
    assert payload[0]["remaining_to_select"] == 2


def test_chosen_course_pass_field_overrides_stale_fail_count() -> None:
    """Use queryChosenCourse.pass when statistics still report failAssessmentCount=0."""
    now = datetime.now()
    ended = (now - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
    stats = {
        "statistical": {
            "group": {
                "55|德育": {
                    "assessmentCount": "2",
                    "selectAssessmentCount": "2",
                    "completeAssessmentCount": "1",
                    "failAssessmentCount": "0",
                    "undoneAssessmentCount": "1",
                }
            }
        }
    }
    selected = [
        {
            "id": 1,
            "courseName": "Passed",
            "courseKind": "德育",
            "courseEndDate": ended,
            "pass": 1,
        },
        {
            "id": 2,
            "courseName": "Failed attendance",
            "courseKind": "德育",
            "courseEndDate": ended,
            "pass": 0,
            "checkin": 0,
        },
    ]
    gaps = parse_gaps(stats, selected_items=selected, now=now)
    assert gaps[0].failed == 1
    assert gaps[0].completed == 1
    assert gaps[0].remaining_to_select == 1
    assert needed_categories(stats, selected_items=selected, now=now) == ["德育"]
    assert not selection_requirements_met(
        stats,
        selected_items=selected,
        now=now,
    )


def test_finished_course_with_failed_checkin_is_not_treated_as_passed() -> None:
    now = datetime.now()
    ended = (now - timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S")
    item = {
        "id": 9,
        "courseName": "Missed sign",
        "courseKind": "美育",
        "courseEndDate": ended,
        "pass": None,
        "checkin": False,
    }
    assert course_assessment_outcome(item, now) == "failed"
