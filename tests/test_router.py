import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from flowroute import CatalogSnapshot, Decision, FlowRouter, RouteRequest, WorkflowRegistry
from flowroute.evaluation import evaluate, load_jsonl

ROOT = Path(__file__).resolve().parents[1]


class RouterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = WorkflowRegistry.from_yaml(ROOT / "examples" / "workflows.yaml")
        cls.router = FlowRouter(cls.registry)

    def test_routes_complete_read_request(self):
        result = self.router.route(RouteRequest(text="Where is order 4812?"))
        self.assertEqual(result.decision, Decision.ROUTE)
        self.assertEqual(result.workflow_id, "orders.get_status")

    def test_clarifies_missing_input(self):
        result = self.router.route(RouteRequest(text="Cancel my meeting tomorrow."))
        self.assertEqual(result.decision, Decision.CLARIFY)
        self.assertEqual(result.missing_inputs, ["event_id"])

    def test_reasoning_request_abstains(self):
        result = self.router.route(RouteRequest(text="Explain quantum entanglement."))
        self.assertEqual(result.decision, Decision.LLM_REQUIRED)
        self.assertEqual(result.reason_code, "OPEN_ENDED_REASONING")

    def test_empty_allowlist_is_not_all_workflows(self):
        result = self.router.route(
            RouteRequest(text="Where is order 4812?", allowed_workflow_ids=[])
        )
        self.assertEqual(result.decision, Decision.LLM_REQUIRED)
        self.assertEqual(result.reason_code, "NO_ELIGIBLE_WORKFLOW")

    def test_context_mutated_after_validation_fails_closed(self):
        request = RouteRequest(
            text="Where is order 4812?",
            context={"order_id": "4812"},
        )
        request.context["invalid"] = float("nan")
        result = self.router.route(request)
        self.assertEqual(result.decision, Decision.LLM_REQUIRED)
        self.assertEqual(result.reason_code, "INVALID_CONTEXT")

    def test_exact_event_still_checks_required_inputs(self):
        result = self.router.route(
            RouteRequest(text="A user registered.", event_type="user_registered")
        )
        self.assertEqual(result.decision, Decision.CLARIFY)
        self.assertEqual(result.missing_inputs, ["recipient"])

    def test_concurrent_routes_do_not_share_fitted_vectorizer_state(self):
        texts = ["Where is order 4812?", "Cancel my meeting tomorrow."] * 8
        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(
                executor.map(lambda text: self.router.route(RouteRequest(text=text)), texts)
            )
        self.assertEqual(
            [result.decision for result in results],
            [Decision.ROUTE, Decision.CLARIFY] * 8,
        )

    def test_catalog_index_is_built_once_and_reused(self):
        retriever = self.router.retriever
        self.assertEqual(retriever.index_build_count, 1)
        self.router.route(RouteRequest(text="Where is order 4812?"))
        self.router.route(RouteRequest(text="Track order ORD-9001"))
        self.assertEqual(retriever.index_build_count, 1)

    def test_fixture_suite(self):
        result = evaluate(self.router, load_jsonl(ROOT / "examples" / "requests.jsonl"))
        self.assertEqual(result.failures, [], result.model_dump_json(indent=2))

    def test_invalid_top_k_is_rejected(self):
        with self.assertRaises(ValueError):
            FlowRouter(self.registry, top_k=0)

    def test_ambiguous_event_rule_abstains(self):
        shared = {
            "version": "1.0.0",
            "description": "Read one record for a trusted application event.",
            "event_types": ["record_changed"],
        }
        snapshot = CatalogSnapshot(
            catalog_version="ambiguous-event",
            workflows=[
                {"id": "records.read_one", "name": "Read one record", **shared},
                {"id": "records.read_backup", "name": "Read backup record", **shared},
            ],
        )
        router = FlowRouter(WorkflowRegistry(snapshot))
        result = router.route(
            RouteRequest(text="A record changed.", event_type="record_changed")
        )
        self.assertEqual(result.decision, Decision.LLM_REQUIRED)
        self.assertEqual(result.reason_code, "AMBIGUOUS_EVENT_RULE")


if __name__ == "__main__":
    unittest.main()
