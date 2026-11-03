import json
import unittest
from types import SimpleNamespace

try:
    from LLM.recommendation.recommendation_agent import RecommendationAgent
except ModuleNotFoundError as exc:
    if exc.name in {"langchain_google_vertexai", "langchain_core", "pydantic"}:
        RecommendationAgent = None
    else:
        raise

AREAS = ["Right knee strength for stairs", "Knee comfort after sitting", "Build up to running 5 km"]
GOOD_PLAN = "We will strengthen your right knee for stairs and prepare for running."
LONG_PLAN = "We will work on your right knee's strength for stairs and start gentle running preparation now."  # > 90


def reply(areas=AREAS, plan=GOOD_PLAN):
    return SimpleNamespace(content=json.dumps({"top_3_action_areas": areas, "next_session_plan": plan}), usage_metadata={})


class FakeLLM:
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), 0

    def invoke(self, messages):
        self.calls += 1
        return self.responses.pop(0)


def make_agent(main, rewriter):
    agent = RecommendationAgent.__new__(RecommendationAgent)  # skip building real Vertex clients
    agent.llm, agent._rewriter = main, rewriter
    return agent


DATA = {"source_data": {"chief_complaint": "Right knee pain on stairs"}}


@unittest.skipIf(RecommendationAgent is None, "backend runtime dependencies are not installed")
class PlanRewriteTests(unittest.TestCase):
    def test_valid_first_answer_makes_a_single_call_and_no_rewrite(self):
        main, rewriter = FakeLLM(reply()), FakeLLM()
        out = make_agent(main, rewriter).generate(DATA)
        self.assertEqual((main.calls, rewriter.calls), (1, 0))
        self.assertEqual(out.next_session_plan, GOOD_PLAN)

    def test_overlong_plan_is_shortened_by_the_small_call_and_areas_are_kept(self):
        self.assertGreater(len(LONG_PLAN), 90)
        main = FakeLLM(reply(plan=LONG_PLAN))
        rewriter = FakeLLM(SimpleNamespace(content='"' + GOOD_PLAN + '"', usage_metadata={}))
        stages = []
        out = make_agent(main, rewriter).generate(DATA, lambda stage, started, **f: stages.append(stage))
        self.assertEqual((main.calls, rewriter.calls), (1, 1))  # no second full call
        self.assertEqual(out.top_3_action_areas, AREAS)
        self.assertEqual(out.next_session_plan, GOOD_PLAN)
        self.assertIn("recommendation_shorten", stages)

    def test_still_invalid_rewrite_falls_back_to_the_full_retry(self):
        main = FakeLLM(reply(plan=LONG_PLAN), reply())
        rewriter = FakeLLM(SimpleNamespace(content=LONG_PLAN, usage_metadata={}))
        out = make_agent(main, rewriter).generate(DATA)
        self.assertEqual((main.calls, rewriter.calls), (2, 1))
        self.assertEqual(out.next_session_plan, GOOD_PLAN)

    def test_rewriter_error_falls_back_to_the_full_retry(self):
        class Broken:
            def invoke(self, messages):
                raise RuntimeError("model unavailable")
        main = FakeLLM(reply(plan=LONG_PLAN), reply())
        out = make_agent(main, Broken()).generate(DATA)
        self.assertEqual(main.calls, 2)
        self.assertEqual(out.next_session_plan, GOOD_PLAN)

    def test_other_problems_skip_the_rewrite_and_use_the_full_retry(self):
        duplicate_areas = [AREAS[0], AREAS[0], AREAS[2]]  # not distinct: not a length problem
        main = FakeLLM(reply(areas=duplicate_areas), reply())
        rewriter = FakeLLM()
        out = make_agent(main, rewriter).generate(DATA)
        self.assertEqual((main.calls, rewriter.calls), (2, 0))
        self.assertEqual(out.top_3_action_areas, AREAS)

    def test_overlong_action_area_is_shortened_alone_and_the_rest_is_kept(self):
        long_area = ["Reduce right knee stiffness after sitting down", AREAS[1], AREAS[2]]  # first is 46 chars
        self.assertGreater(len(long_area[0]), 40)
        main = FakeLLM(reply(areas=long_area))
        rewriter = FakeLLM(SimpleNamespace(content="Reduce right knee stiffness sitting", usage_metadata={}))
        out = make_agent(main, rewriter).generate(DATA)
        self.assertEqual((main.calls, rewriter.calls), (1, 1))
        self.assertEqual(out.top_3_action_areas, ["Reduce right knee stiffness sitting", AREAS[1], AREAS[2]])
        self.assertEqual(out.next_session_plan, GOOD_PLAN)

    def test_area_and_plan_both_long_are_each_shortened(self):
        long_area = [AREAS[0], "Reduce right knee stiffness after sitting down", AREAS[2]]
        main = FakeLLM(reply(areas=long_area, plan=LONG_PLAN))
        rewriter = FakeLLM(SimpleNamespace(content="Reduce right knee stiffness sitting", usage_metadata={}),
                           SimpleNamespace(content=GOOD_PLAN, usage_metadata={}))
        out = make_agent(main, rewriter).generate(DATA)
        self.assertEqual((main.calls, rewriter.calls), (1, 2))
        self.assertEqual(out.next_session_plan, GOOD_PLAN)

    def test_rewrite_that_chops_a_word_is_rejected_and_the_full_retry_is_used(self):
        long_area = ["Reduce right knee stiffness after sitting", AREAS[1], AREAS[2]]  # 41 chars
        main = FakeLLM(reply(areas=long_area), reply())
        rewriter = FakeLLM(SimpleNamespace(content="Reduce right knee stiffness after sit", usage_metadata={}))
        out = make_agent(main, rewriter).generate(DATA)
        self.assertEqual((main.calls, rewriter.calls), (2, 1))  # chopped "sitting" -> "sit": not accepted
        self.assertEqual(out.top_3_action_areas, AREAS)

    def test_two_bad_answers_still_raise_instead_of_saving_something_invalid(self):
        main = FakeLLM(reply(plan=LONG_PLAN), reply(plan=LONG_PLAN))
        rewriter = FakeLLM(SimpleNamespace(content=LONG_PLAN, usage_metadata={}))
        with self.assertRaises(RuntimeError):
            make_agent(main, rewriter).generate(DATA)


if __name__ == "__main__":
    unittest.main()
