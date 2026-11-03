from boya_kit.gaps import (
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
    assert gaps[1].needs_more is False
    assert gaps[1].remaining_to_pass == 1


def test_needed_categories() -> None:
    assert needed_categories(sample_statistics()) == ["德育"]
    assert not requirements_met(sample_statistics())
    assert not selection_requirements_met(sample_statistics())
    assert selection_requirements_met(
        sample_statistics(),
        exclude={"德育"},
    )


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
