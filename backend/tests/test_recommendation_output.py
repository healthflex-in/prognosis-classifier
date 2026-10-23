"""Offline regression tests: no Google calls, database writes or real patient data."""
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from pydantic import ValidationError

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from utils.recommendation_output import RecommendationOutput, valid_cached_recommendation


@pytest.fixture
def agent():
    # Exercise the actual agent implementation with only its Vertex transport
    # replaced. Prevent dotenv from loading local credentials during tests.
    vertex = ModuleType("langchain_google_vertexai")
    vertex.ChatVertexAI = Mock()
    spec = importlib.util.spec_from_file_location(
        "tested_recommendation_agent", BACKEND / "LLM/recommendation/recommendation_agent.py"
    )
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"langchain_google_vertexai": vertex}), patch("dotenv.load_dotenv"):
        spec.loader.exec_module(module)
    instance = module.RecommendationAgent.__new__(module.RecommendationAgent)
    instance.llm = Mock()
    return instance


def valid_data():
    return {
        "top_3_action_areas": ["Improve right knee movement", "Build calf strength for running", "Ease right knee pain on stairs"],
        "next_session_plan": "We will work on right knee movement and gentle strengthening.",
    }


def response(data):
    return SimpleNamespace(content=json.dumps(data))


def test_valid_response_is_not_rewritten_or_truncated(agent):
    expected = valid_data()
    agent.llm.invoke.return_value = response(expected)
    assert agent.generate({}).model_dump() == expected
    agent.llm.invoke.assert_called_once()


@pytest.mark.parametrize("field", ["area", "plan"])
def test_overlong_output_is_rewritten_not_sliced(agent, field):
    original = valid_data()
    if field == "area":
        original["top_3_action_areas"][0] = "Improve right knee movement for walking up stairs comfortably"
    else:
        original["next_session_plan"] = "We will work on improving your right knee's bending range and start gentle strengthening for stair climbing."
    calls = []
    outputs = iter([response(original), response(valid_data())])

    def invoke(messages):
        calls.append(list(messages))
        return next(outputs)

    agent.llm.invoke.side_effect = invoke
    result = agent.generate({"source_data": {"chief_complaint": "Right knee pain on stairs"}})
    assert result.model_dump() == valid_data()
    assert len(calls) == 2
    assert json.loads(calls[1][-2].content) == original
    assert "40 characters" in calls[1][-1].content
    assert "90 characters" in calls[1][-1].content
    assert "Right knee pain on stairs" in calls[1][1].content


@pytest.mark.parametrize("plan", [
    "We'll work on improving your right knee's bending range and start gentle strengthening for",
    "We'll start hands-on work for your right hip and begin gentle strengthening for your right",
    "We will start with hands-on work for your left knee and begin specific strengthening exerc",
    "We will focus on reducing your R knee pain and improving quadriceps strength for daily act",
    "We will work on strengthening for.",
    "We will work on knee movement...",
])
def test_cut_off_plans_are_rewritten_and_not_reused_from_cache(agent, plan):
    bad = {**valid_data(), "next_session_plan": plan}
    assert not valid_cached_recommendation(bad)
    agent.llm.invoke.side_effect = [response(bad), response(valid_data())]
    assert agent.generate({}).next_session_plan == valid_data()["next_session_plan"]
    assert agent.llm.invoke.call_count == 2


@pytest.mark.parametrize("bad", [
    {**valid_data(), "top_3_action_areas": ["Knee movement"]},
    {**valid_data(), "top_3_action_areas": ["Knee movement", " ", "Calf strength"]},
    {**valid_data(), "top_3_action_areas": ["Knee movement"] * 3},
    {**valid_data(), "top_3_action_areas": ["One", "Two", "Three", "Four"]},
    {**valid_data(), "next_session_plan": " "},
    [],
])
def test_invalid_output_is_rejected_after_one_rewrite(agent, bad):
    agent.llm.invoke.return_value = response(bad)
    with pytest.raises(RuntimeError, match="Could not generate complete recommendations"):
        agent.generate({})
    assert agent.llm.invoke.call_count == 2


def test_invalid_json_can_be_rewritten(agent):
    agent.llm.invoke.side_effect = [SimpleNamespace(content="not json"), response(valid_data())]
    assert agent.generate({}).model_dump() == valid_data()


def test_api_failure_is_not_returned_as_successful_generic_recommendations(agent):
    agent.llm.invoke.side_effect = RuntimeError("Transport unavailable")
    with pytest.raises(RuntimeError, match="Recommendation generation failed"):
        agent.generate({})
    agent.llm.invoke.assert_called_once()


def test_limits_include_spaces_and_punctuation():
    data = valid_data()
    data["top_3_action_areas"][0] = "a" * 40
    data["next_session_plan"] = "We will review " + "a" * 74 + "."
    assert len(data["next_session_plan"]) == 90
    assert RecommendationOutput.model_validate(data).model_dump() == data
    for invalid in (
        {**data, "top_3_action_areas": ["a" * 41, "Two", "Three"]},
        {**data, "next_session_plan": data["next_session_plan"][:-1] + "a."},
    ):
        with pytest.raises(ValidationError):
            RecommendationOutput.model_validate(invalid)


def test_valid_cached_record_remains_reusable():
    assert valid_cached_recommendation({**valid_data(), "patient_id": "test", "input_hash": "abc"})
    assert not valid_cached_recommendation(None)
