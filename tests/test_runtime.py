import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import yaml

from flowroute import (
    ArtifactManifest,
    CalibrationConfig,
    CandidateScore,
    Decision,
    FlowRouter,
    ProductionConfigurationError,
    RetrievalHit,
    RouteRequest,
    RouterRuntime,
    RouterRuntimeConfig,
    RuntimeGenerationError,
    VerificationLabel,
    WorkflowRegistry,
    load_production_router,
    sha256_path,
)
from flowroute.serialization import SERIALIZER_VERSION

ROOT = Path(__file__).resolve().parents[1]


class StubRetriever:
    model_version = "stub-retriever@sha256:01"
    production_capable = True

    def __init__(self):
        self.prepare_calls = 0

    def prepare(self, workflows):
        self.prepare_calls += 1

    def rank(self, query, workflows, *, top_k):
        return [
            RetrievalHit(workflow_id=item.id, score=0.99 - (index * 0.2), rank=index + 1)
            for index, item in enumerate(workflows[:top_k])
        ]


class StubVerifier:
    model_version = "stub-verifier@sha256:02"
    production_capable = True

    def verify(self, query, context, contract, retrieval):
        return CandidateScore(
            workflow_id=contract.id,
            risk_tier=contract.risk_tier,
            retrieval_score=retrieval.score,
            executable_score=0.99,
            needs_input_score=0.0,
            mismatch_score=0.01,
            label=VerificationLabel.EXECUTABLE,
        )


class FailingRetriever(StubRetriever):
    def rank(self, query, workflows, *, top_k):
        raise RuntimeError("model server unavailable")


class FactoryRetriever(StubRetriever):
    def __init__(
        self,
        _model_path,
        *,
        model_version,
        query_prefix,
        document_prefix,
    ):
        super().__init__()
        self.model_version = model_version
        self.query_prefix = query_prefix
        self.document_prefix = document_prefix


class FactoryVerifier(StubVerifier):
    def __init__(self, _model_path, *, model_version):
        self.model_version = model_version


def manifest_for(registry, calibration, *, policy=None, top_k=1, **updates):
    from flowroute.policy import RoutingPolicy

    policy = policy or RoutingPolicy()
    values = {
        "bundle_version": "test-bundle-1",
        "created_at": datetime.now(timezone.utc),
        "catalog_version": registry.catalog_version,
        "catalog_content_hash": registry.content_hash,
        "serializer_version": SERIALIZER_VERSION,
        "retriever_model_version": StubRetriever.model_version,
        "verifier_model_version": StubVerifier.model_version,
        "calibration_version": calibration.version,
        "calibration_content_hash": calibration.content_hash,
        "policy_content_hash": policy.content_hash,
        "top_k": top_k,
        "allow_exact_event_routes": False,
        "artifact_hashes": {
            "retriever": "1" * 64,
            "verifier": "2" * 64,
        },
        "approved_for_production": True,
        "approval_reference": "test-approval",
    }
    values.update(updates)
    return ArtifactManifest(**values)


def production_router(*, max_context_bytes=64 * 1024):
    registry = WorkflowRegistry.from_yaml(ROOT / "examples" / "workflows.yaml")
    calibration = CalibrationConfig.from_yaml(ROOT / "configs" / "calibration.yaml")
    return FlowRouter(
        registry,
        retriever=StubRetriever(),
        verifier=StubVerifier(),
        calibration=calibration,
        runtime_config=RouterRuntimeConfig.production(
            max_context_bytes=max_context_bytes
        ),
        artifact_manifest=manifest_for(registry, calibration),
        top_k=1,
    )


class ProductionRuntimeTests(unittest.TestCase):
    def test_production_rejects_lexical_defaults(self):
        registry = WorkflowRegistry.from_yaml(ROOT / "examples" / "workflows.yaml")
        with self.assertRaises(ProductionConfigurationError):
            FlowRouter(
                registry,
                runtime_config=RouterRuntimeConfig.production(),
            )

    def test_production_rejects_incompatible_manifest(self):
        registry = WorkflowRegistry.from_yaml(ROOT / "examples" / "workflows.yaml")
        calibration = CalibrationConfig.from_yaml(ROOT / "configs" / "calibration.yaml")
        manifest = manifest_for(
            registry,
            calibration,
            catalog_content_hash="f" * 64,
        )
        with self.assertRaises(ProductionConfigurationError):
            FlowRouter(
                registry,
                retriever=StubRetriever(),
                verifier=StubVerifier(),
                calibration=calibration,
                runtime_config=RouterRuntimeConfig.production(),
                artifact_manifest=manifest,
            )

    def test_production_requires_catalog_version_and_allowlist(self):
        router = production_router()
        missing_version = router.route(RouteRequest(text="Where is order 4812?"))
        self.assertEqual(missing_version.decision, Decision.LLM_REQUIRED)
        self.assertEqual(missing_version.reason_code, "CATALOG_VERSION_REQUIRED")

        missing_allowlist = router.route(
            RouteRequest(
                text="Where is order 4812?",
                catalog_version=router.registry.catalog_version,
            )
        )
        self.assertEqual(missing_allowlist.decision, Decision.LLM_REQUIRED)
        self.assertEqual(missing_allowlist.reason_code, "WORKFLOW_ALLOWLIST_REQUIRED")

    def test_complete_production_request_routes(self):
        router = production_router()
        result = router.route(
            RouteRequest(
                text="Where is order 4812?",
                catalog_version=router.registry.catalog_version,
                allowed_workflow_ids=["orders.get_status"],
            )
        )
        self.assertEqual(result.decision, Decision.ROUTE)
        self.assertEqual(result.runtime_mode, "production")

    def test_production_disables_debug(self):
        router = production_router()
        result = router.route(
            RouteRequest(
                text="Where is order 4812?",
                catalog_version=router.registry.catalog_version,
                allowed_workflow_ids=["orders.get_status"],
                debug=True,
            )
        )
        self.assertEqual(result.reason_code, "DEBUG_DISABLED")
        self.assertIsNone(result.candidates)

    def test_production_does_not_trust_exact_event_by_default(self):
        router = production_router()
        result = router.route(
            RouteRequest(
                text="Explain the status to me",
                context={"recipient": "new-user@example.com"},
                event_type="user_registered",
                catalog_version=router.registry.catalog_version,
                allowed_workflow_ids=["communications.send_welcome_email"],
            )
        )
        self.assertEqual(result.decision, Decision.LLM_REQUIRED)
        self.assertEqual(result.reason_code, "OPEN_ENDED_REASONING")

    def test_production_detects_calibration_mutation(self):
        from flowroute import RiskTier, TierThreshold

        router = production_router()
        router.calibration.tiers[RiskTier.LOW] = TierThreshold(
            route=0.99,
            margin=0.99,
        )
        self.assertFalse(RouterRuntime(router).snapshot().ready)
        with self.assertLogs("flowroute", level="ERROR"):
            result = router.route(
                RouteRequest(
                    text="Where is order 4812?",
                    catalog_version=router.registry.catalog_version,
                    allowed_workflow_ids=["orders.get_status"],
                )
            )
        self.assertEqual(result.reason_code, "RUNTIME_INTEGRITY_FAILURE")

    def test_shadow_mode_fails_closed_on_backend_error(self):
        registry = WorkflowRegistry.from_yaml(ROOT / "examples" / "workflows.yaml")
        router = FlowRouter(
            registry,
            retriever=FailingRetriever(),
            verifier=StubVerifier(),
            runtime_config=RouterRuntimeConfig.shadow(),
        )
        with self.assertLogs("flowroute", level="ERROR"):
            result = router.route(
                RouteRequest(
                    text="Where is order 4812?",
                    catalog_version=registry.catalog_version,
                    allowed_workflow_ids=["orders.get_status"],
                )
            )
        self.assertEqual(result.decision, Decision.LLM_REQUIRED)
        self.assertEqual(result.reason_code, "BACKEND_UNAVAILABLE")

    def test_context_limit_fails_closed(self):
        router = production_router(max_context_bytes=1_024)
        result = router.route(
            RouteRequest(
                text="Where is order 4812?",
                context={"padding": "x" * 2_000},
                catalog_version=router.registry.catalog_version,
                allowed_workflow_ids=["orders.get_status"],
            )
        )
        self.assertEqual(result.reason_code, "CONTEXT_TOO_LARGE")

    def test_atomic_replace_and_rollback(self):
        first = production_router()
        second = production_router()
        runtime = RouterRuntime(first)
        replaced = runtime.replace(second, expected_generation=1)
        self.assertEqual(replaced.generation, 2)
        rolled_back = runtime.rollback(expected_generation=2)
        self.assertEqual(rolled_back.generation, 3)
        self.assertIs(runtime.current, first)
        with self.assertRaises(RuntimeGenerationError):
            runtime.replace(second, expected_generation=2)

    def test_atomic_reload_cannot_downgrade_runtime_mode(self):
        runtime = RouterRuntime(production_router())
        registry = WorkflowRegistry.from_yaml(ROOT / "examples" / "workflows.yaml")
        with self.assertRaises(ProductionConfigurationError):
            runtime.replace(FlowRouter(registry), expected_generation=1)

    def test_directory_hash_changes_with_artifact_content(self):
        with TemporaryDirectory() as directory:
            artifact = Path(directory)
            first_file = artifact / "config.json"
            first_file.write_text('{"version": 1}', encoding="utf-8")
            first_hash = sha256_path(artifact)
            first_file.write_text('{"version": 2}', encoding="utf-8")
            second_hash = sha256_path(artifact)
        self.assertEqual(len(first_hash), 64)
        self.assertNotEqual(first_hash, second_hash)

    def test_production_factory_verifies_and_warms_local_artifacts(self):
        registry = WorkflowRegistry.from_yaml(ROOT / "examples" / "workflows.yaml")
        calibration = CalibrationConfig.from_yaml(ROOT / "configs" / "calibration.yaml")
        with TemporaryDirectory() as directory:
            release = Path(directory)
            retriever_path = release / "retriever"
            verifier_path = release / "verifier"
            retriever_path.mkdir()
            verifier_path.mkdir()
            (retriever_path / "config.json").write_text("{}", encoding="utf-8")
            (verifier_path / "config.json").write_text("{}", encoding="utf-8")
            manifest = manifest_for(
                registry,
                calibration,
                artifact_hashes={
                    "retriever": sha256_path(retriever_path),
                    "verifier": sha256_path(verifier_path),
                },
            )
            manifest_path = release / "artifact-manifest.yaml"
            manifest_path.write_text(
                yaml.safe_dump(manifest.model_dump(mode="json"), sort_keys=False),
                encoding="utf-8",
            )
            with (
                patch("flowroute.factory.HuggingFaceRetriever", FactoryRetriever),
                patch(
                    "flowroute.factory.HuggingFaceCrossEncoderVerifier",
                    FactoryVerifier,
                ),
            ):
                router = load_production_router(
                    catalog_path=ROOT / "examples" / "workflows.yaml",
                    calibration_path=ROOT / "configs" / "calibration.yaml",
                    artifact_manifest_path=manifest_path,
                    retriever_model=retriever_path,
                    verifier_model=verifier_path,
                    top_k=1,
                )
        self.assertEqual(router.runtime_config.mode, "production")
        self.assertEqual(router.retriever.prepare_calls, 1)


if __name__ == "__main__":
    unittest.main()
