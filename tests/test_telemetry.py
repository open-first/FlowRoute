import io
import logging
import unittest
from pathlib import Path

from flowroute import (
    CallbackTelemetrySink,
    FlowRouter,
    InMemoryTelemetrySink,
    LoggingTelemetrySink,
    RouteRequest,
    WorkflowRegistry,
)

ROOT = Path(__file__).resolve().parents[1]


class TelemetryTests(unittest.TestCase):
    def setUp(self):
        self.registry = WorkflowRegistry.from_yaml(ROOT / "examples" / "workflows.yaml")

    def test_in_memory_sink_receives_decision(self):
        sink = InMemoryTelemetrySink()
        router = FlowRouter(self.registry, telemetry=sink)
        result = router.route(RouteRequest(text="Where is order 4812?"))
        events = sink.snapshot()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].request_id, result.request_id)

    def test_logging_sink_omits_request_text_and_context(self):
        stream = io.StringIO()
        logger = logging.getLogger("flowroute.test.telemetry")
        logger.handlers = []
        logger.propagate = False
        logger.setLevel(logging.INFO)
        logger.addHandler(logging.StreamHandler(stream))
        router = FlowRouter(
            self.registry,
            telemetry=LoggingTelemetrySink(logger),
        )
        router.route(
            RouteRequest(
                text="Where is order SECRET-4812?",
                context={"private": "SECRET-CONTEXT"},
            )
        )
        output = stream.getvalue()
        self.assertIn("flowroute.decision", output)
        self.assertNotIn("SECRET-4812", output)
        self.assertNotIn("SECRET-CONTEXT", output)

    def test_telemetry_failure_does_not_change_route(self):
        def fail(_response):
            raise RuntimeError("telemetry unavailable")

        router = FlowRouter(
            self.registry,
            telemetry=CallbackTelemetrySink(fail),
        )
        with self.assertLogs("flowroute", level="ERROR"):
            result = router.route(RouteRequest(text="Where is order 4812?"))
        self.assertEqual(result.workflow_id, "orders.get_status")


if __name__ == "__main__":
    unittest.main()
