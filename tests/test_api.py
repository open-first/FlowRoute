import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

FASTAPI_AVAILABLE = importlib.util.find_spec("fastapi") is not None
HTTPX_AVAILABLE = importlib.util.find_spec("httpx") is not None


@unittest.skipUnless(FASTAPI_AVAILABLE and HTTPX_AVAILABLE, "install FlowRoute API and dev extras")
class ApiTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        from flowroute.api import create_app
        from flowroute.registry import WorkflowRegistry
        from flowroute.router import FlowRouter

        root = Path(__file__).resolve().parents[1]
        registry = WorkflowRegistry.from_yaml(root / "examples" / "workflows.yaml")
        cls.app = create_app(FlowRouter(registry))

    async def asyncSetUp(self):
        import httpx

        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app), base_url="http://test"
        )

    async def asyncTearDown(self):
        await self.client.aclose()

    async def test_health(self):
        response = await self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["catalog_version"], "demo-2026-09-04")
        self.assertEqual(response.json()["generation"], 1)

    async def test_liveness_and_readiness(self):
        live = await self.client.get("/health/live")
        ready = await self.client.get("/health/ready")
        self.assertEqual(live.status_code, 200)
        self.assertEqual(ready.status_code, 200)
        self.assertTrue(ready.json()["ready"])

    async def test_readiness_returns_503_when_bundle_is_not_ready(self):
        import httpx

        from flowroute.api import create_app
        from flowroute.registry import WorkflowRegistry
        from flowroute.router import FlowRouter

        root = Path(__file__).resolve().parents[1]
        registry = WorkflowRegistry.from_yaml(root / "examples" / "workflows.yaml")
        router = FlowRouter(registry)
        with patch.object(router, "is_ready", return_value=False):
            app = create_app(router)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                response = await client.get("/health/ready")
        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.json()["ready"])

    async def test_route(self):
        response = await self.client.post(
            "/v1/route",
            json={"text": "Where is order 4812?", "catalog_version": "demo-2026-09-04"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["decision"], "ROUTE")
        self.assertEqual(response.json()["workflow_id"], "orders.get_status")

    async def test_request_id_is_returned(self):
        response = await self.client.post(
            "/v1/route",
            headers={"x-request-id": "req-client-17"},
            json={"text": "Where is order 4812?"},
        )
        self.assertEqual(response.headers["x-request-id"], "req-client-17")
        self.assertEqual(response.json()["request_id"], "req-client-17")

    async def test_body_limit_is_enforced(self):
        import httpx

        from flowroute.api import ApiSettings, create_app
        from flowroute.registry import WorkflowRegistry
        from flowroute.router import FlowRouter

        root = Path(__file__).resolve().parents[1]
        registry = WorkflowRegistry.from_yaml(root / "examples" / "workflows.yaml")
        app = create_app(
            FlowRouter(registry),
            settings=ApiSettings(max_body_bytes=1_024),
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/v1/route",
                json={"text": "x" * 2_000},
            )
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json()["error"], "REQUEST_TOO_LARGE")

    async def test_streamed_body_limit_is_enforced_without_content_length(self):
        import httpx

        from flowroute.api import ApiSettings, create_app
        from flowroute.registry import WorkflowRegistry
        from flowroute.router import FlowRouter

        root = Path(__file__).resolve().parents[1]
        registry = WorkflowRegistry.from_yaml(root / "examples" / "workflows.yaml")
        app = create_app(
            FlowRouter(registry),
            settings=ApiSettings(max_body_bytes=1_024),
        )

        async def chunks():
            yield b'{"text":"'
            yield b"x" * 2_000
            yield b'"}'

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/v1/route",
                content=chunks(),
                headers={"content-type": "application/json"},
            )
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json()["error"], "REQUEST_TOO_LARGE")

    async def test_authorizer_can_only_reduce_client_access(self):
        import httpx

        from flowroute.api import ApiSettings, create_app
        from flowroute.registry import WorkflowRegistry
        from flowroute.router import FlowRouter

        root = Path(__file__).resolve().parents[1]
        registry = WorkflowRegistry.from_yaml(root / "examples" / "workflows.yaml")

        def authorize(_request, _payload):
            return ["orders.get_status"]

        app = create_app(
            FlowRouter(registry),
            authorizer=authorize,
            settings=ApiSettings(require_authorizer=True),
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/v1/route",
                json={
                    "text": "Refund payment pay_90210.",
                    "allowed_workflow_ids": ["billing.refund_payment"],
                },
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["decision"], "LLM_REQUIRED")
        self.assertEqual(response.json()["reason_code"], "NO_ELIGIBLE_WORKFLOW")

    async def test_authorization_denial_returns_403(self):
        import httpx

        from flowroute.api import AuthorizationDenied, create_app
        from flowroute.registry import WorkflowRegistry
        from flowroute.router import FlowRouter

        root = Path(__file__).resolve().parents[1]
        registry = WorkflowRegistry.from_yaml(root / "examples" / "workflows.yaml")

        def authorize(_request, _payload):
            raise AuthorizationDenied()

        app = create_app(FlowRouter(registry), authorizer=authorize)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/v1/route",
                json={"text": "Where is order 4812?"},
            )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"]["error"], "AUTHORIZATION_DENIED")

    async def test_invalid_authorizer_result_fails_closed(self):
        import httpx

        from flowroute.api import create_app
        from flowroute.registry import WorkflowRegistry
        from flowroute.router import FlowRouter

        root = Path(__file__).resolve().parents[1]
        registry = WorkflowRegistry.from_yaml(root / "examples" / "workflows.yaml")

        def authorize(_request, _payload):
            return ["NOT A VALID WORKFLOW ID"]

        app = create_app(FlowRouter(registry), authorizer=authorize)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            with self.assertLogs("flowroute.api", level="ERROR"):
                response = await client.post(
                    "/v1/route",
                    json={"text": "Where is order 4812?"},
                )
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["detail"]["error"], "AUTHORIZATION_INVALID")

    async def test_required_authorizer_is_checked_at_startup(self):
        from flowroute.api import ApiSettings, create_app
        from flowroute.registry import WorkflowRegistry
        from flowroute.router import FlowRouter
        from flowroute.runtime import ProductionConfigurationError

        root = Path(__file__).resolve().parents[1]
        registry = WorkflowRegistry.from_yaml(root / "examples" / "workflows.yaml")
        with self.assertRaises(ProductionConfigurationError):
            create_app(
                FlowRouter(registry),
                settings=ApiSettings(require_authorizer=True),
            )

    async def test_production_settings_reject_malformed_hosts_and_origins(self):
        from pydantic import ValidationError

        from flowroute.api import ApiSettings

        with self.assertRaises(ValidationError):
            ApiSettings.production_defaults(
                trusted_hosts=["https://router.example.test"],
            )
        with self.assertRaises(ValidationError):
            ApiSettings.production_defaults(
                trusted_hosts=["router.example.test"],
                cors_origins=["https://client.example.test/path"],
            )

    async def test_stale_catalog_returns_conflict(self):
        response = await self.client.post(
            "/v1/route", json={"text": "Where is order 4812?", "catalog_version": "stale"}
        )
        self.assertEqual(response.status_code, 409)


if __name__ == "__main__":
    unittest.main()
