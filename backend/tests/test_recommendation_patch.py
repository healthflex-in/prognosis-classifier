"""Offline validation checks for clinician recommendation edits."""
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from api.routes.recommendation import RecommendationPatch


@pytest.mark.parametrize("value", [None, [], ["One"], ["One", "Two", " "], ["", "", ""], ["A", "B", "C", "D"]])
def test_incomplete_action_areas_rejected(value):
    with pytest.raises(ValidationError):
        RecommendationPatch(top_3_action_areas=value)


@pytest.mark.parametrize("value", [None, "", " \n\t "])
def test_blank_plan_rejected(value):
    with pytest.raises(ValidationError):
        RecommendationPatch(next_session_plan=value)


def test_valid_edits_trimmed():
    patch = RecommendationPatch(top_3_action_areas=[" A ", "B", "C"], next_session_plan=" Review ")
    assert patch.top_3_action_areas == ["A", "B", "C"]
    assert patch.next_session_plan == "Review"


def test_partial_edits_preserve_omitted_fields():
    assert RecommendationPatch(next_session_plan="Review").model_dump(exclude_unset=True) == {"next_session_plan": "Review"}
    assert RecommendationPatch(top_3_action_areas=["A", "B", "C"]).model_dump(exclude_unset=True) == {"top_3_action_areas": ["A", "B", "C"]}
