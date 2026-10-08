"""Shared validation for generated recommendations and generation-cache hits."""
import re
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints, ValidationError, field_validator

ActionArea = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=40)]
SessionPlan = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=90)]


class RecommendationOutput(BaseModel):
    top_3_action_areas: list[ActionArea] = Field(min_length=3, max_length=3)
    next_session_plan: SessionPlan

    @field_validator("top_3_action_areas")
    @classmethod
    def distinct_areas(cls, areas):
        if len({area.casefold() for area in areas}) != 3:
            raise ValueError("Return three distinct action areas")
        return areas

    @field_validator("next_session_plan")
    @classmethod
    def complete_plan(cls, plan):
        # This catches visibly unfinished responses. Full grammatical quality
        # still depends on the model; punctuation alone cannot prove it.
        if not plan.endswith((".", "!", "?")) or plan.endswith(("...", "…")):
            raise ValueError("Write a complete next-session sentence ending with punctuation")
        words = re.findall(r"[A-Za-z]+", plan)
        if not words or words[-1].lower() in {"for", "with", "and", "or", "the", "your", "to", "of"}:
            raise ValueError("Finish the next-session sentence; do not leave a dangling word")
        return plan


def valid_cached_recommendation(document):
    if not document:
        return False
    try:
        RecommendationOutput.model_validate(document)
        return True
    except ValidationError:
        return False
