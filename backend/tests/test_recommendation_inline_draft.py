import unittest

try:
    from api.routes.partial_reports import PartialReportPayload, build_inline_partial, compute_partial_hash
    from api.recommendation_draft import prepare_recommendation
except ModuleNotFoundError as exc:
    if exc.name in {"fastapi", "pymongo", "bson", "pydantic"}:
        build_inline_partial = None
    else:
        raise

RID = "000000000000000000000002"


def draft():
    return dict(report_id=RID, chief_complaint="Knee pain", client_history="After running",
                subjective_assessment="Pain on stairs", provisional_diagnosis="Knee pain",
                nprs=3, short_term_goals=[{"goal": "Climb stairs"}],
                objective_assessment={"tests": [{"testName": "Knee flexion", "value": 90}]},
                recommendations=[{"plans": "Strengthening"}])


@unittest.skipIf(build_inline_partial is None, "backend runtime dependencies are not installed")
class InlineDraftTests(unittest.TestCase):
    def test_hash_matches_what_the_draft_post_stores(self):
        # The POST route validates the draft together with prognosis_text, pops it, then hashes.
        # prognosis_text only exists on the route when early prognosis start is installed.
        extra = {"prognosis_text": {"chief_complaint": "Knee pain \n"}} \
            if "prognosis_text" in PartialReportPayload.model_fields else {}
        stored = PartialReportPayload(**draft(), **extra).model_dump()
        stored.pop("prognosis_text", None)
        self.assertEqual(build_inline_partial(draft())["hash"], compute_partial_hash(stored))
        self.assertEqual(build_inline_partial(draft())["fields"], stored)

    def test_inline_partial_feeds_prepare_recommendation_like_a_stored_draft(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        import sys
        from bson import ObjectId
        sys.modules["utils.vald_extractor"] = SimpleNamespace(extract_vald_first_session=lambda *_: {})
        db = SimpleNamespace(users=SimpleNamespace(find_one=Mock(return_value={"_id": 1})),
                             reports=SimpleNamespace(find_one=Mock(return_value={"_id": 2})))
        pid = "000000000000000000000001"
        data, hashed = prepare_recommendation(db, pid, build_inline_partial(draft()), RID)
        self.assertEqual(data["source_data"]["chief_complaint"], "Knee pain")
        self.assertEqual(len(hashed), 64)

    def test_incomplete_draft_is_rejected(self):
        bad = draft()
        bad["short_term_goals"] = []
        with self.assertRaises(ValueError):
            build_inline_partial(bad)


if __name__ == "__main__":
    unittest.main()
