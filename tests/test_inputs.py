import unittest

from flowroute.inputs import resolve_required_inputs
from flowroute.models import WorkflowContract


class InputResolutionTests(unittest.TestCase):
    def test_structured_context_takes_precedence_over_regex(self):
        contract = WorkflowContract(
            id="orders.lookup",
            version="1.0.0",
            name="Look up order",
            description="Look up one order using its stable identifier.",
            required_inputs=[
                {
                    "name": "order_id",
                    "pattern": r"order (?P<value>[0-9]+)",
                }
            ],
        )
        resolution = resolve_required_inputs(
            contract,
            "order 123",
            {"order_id": "trusted-456"},
        )
        self.assertEqual(resolution.values["order_id"], "trusted-456")
        self.assertEqual(resolution.extraction_timeouts, [])

    def test_pathological_regex_times_out_fail_closed(self):
        contract = WorkflowContract(
            id="records.lookup",
            version="1.0.0",
            name="Look up record",
            description="Look up one record using a supplied text identifier.",
            required_inputs=[
                {
                    "name": "record_id",
                    "pattern": r"(a|aa)+$",
                }
            ],
        )
        resolution = resolve_required_inputs(
            contract,
            ("a" * 8_000) + "!",
            {},
            regex_timeout_seconds=0.000001,
        )
        self.assertEqual(resolution.values, {})
        self.assertEqual(resolution.missing, ["record_id"])
        self.assertEqual(resolution.extraction_timeouts, ["record_id"])


if __name__ == "__main__":
    unittest.main()
