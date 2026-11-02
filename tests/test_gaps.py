from boya_kit.gaps import needed_categories, parse_gaps, requirements_met


def sample_statistics() -> dict:
    return {
        "validCount": 2,
        "statistical": {
            "group": {
                "1|德育": {
                    "assessmentCount": "2",
                    "selectAssessmentCount": "1",
                    "completeAssessmentCount": "2",
                    "failAssessmentCount": "0",
                    "undoneAssessmentCount": "0",
                },
                "2|美育": {
                    "assessmentCount": "1",
                    "selectAssessmentCount": "1",
                    "completeAssessmentCount": "0",
                    "failAssessmentCount": "0",
                    "undoneAssessmentCount": "1",
                },
            }
        },
    }


def test_parse_gaps() -> None:
    gaps = parse_gaps(sample_statistics())
    assert [gap.category for gap in gaps] == ["德育", "美育"]
    assert gaps[1].needs_more


def test_needed_categories() -> None:
    assert needed_categories(sample_statistics()) == ["美育"]
    assert not requirements_met(sample_statistics())
    assert requirements_met(sample_statistics(), exclude={"美育"})
