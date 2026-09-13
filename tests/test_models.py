import unittest
from datetime import datetime

from pydantic import ValidationError

from flowroute.models import CatalogSnapshot, RouteRequest, WorkflowContract


class ContractValidationTests(unittest.TestCase):
    def test_input_shorthand_is_expanded(self):
        contract = WorkflowContract(
            id="orders.lookup",
            version="1.0.0",
            name="Look up order",
            description="Look up one order using its stable identifier.",
            required_inputs=["order_id"],
        )
        self.assertEqual(contract.required_inputs[0].name, "order_id")

    def test_external_write_requires_safety_boundary(self):
        with self.assertRaises(ValidationError):
            WorkflowContract(
                id="email.send",
                version="1.0.0",
                name="Send an email",
                description="Send one email message to one recipient.",
                side_effect="external_write",
            )

    def test_duplicate_active_workflow_is_rejected(self):
        raw = dict(
            id="orders.lookup",
            version="1.0.0",
            name="Look up order",
            description="Look up one order using its stable identifier.",
        )
        with self.assertRaises(ValidationError):
            CatalogSnapshot(catalog_version="v1", workflows=[raw, raw])

    def test_request_context_must_be_json_serializable(self):
        with self.assertRaises(ValidationError):
            RouteRequest(text="Look up the order", context={"when": datetime.now()})

    def test_request_workflow_lists_reject_duplicates(self):
        with self.assertRaises(ValidationError):
            RouteRequest(
                text="Look up the order",
                allowed_workflow_ids=["orders.lookup", "orders.lookup"],
            )


if __name__ == "__main__":
    unittest.main()
