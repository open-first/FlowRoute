"""Factories for loading complete, compatibility-checked router bundles."""

from __future__ import annotations

from pathlib import Path

from .backends import HuggingFaceCrossEncoderVerifier, HuggingFaceRetriever
from .calibration import CalibrationConfig
from .registry import WorkflowRegistry
from .router import FlowRouter
from .runtime import ArtifactManifest, RouterRuntimeConfig
from .telemetry import LoggingTelemetrySink, TelemetrySink


def load_production_router(
    *,
    catalog_path: str | Path,
    calibration_path: str | Path,
    artifact_manifest_path: str | Path,
    retriever_model: str | Path,
    verifier_model: str | Path,
    telemetry: TelemetrySink | None = None,
    query_prefix: str = "",
    document_prefix: str = "",
    top_k: int = 8,
    max_context_bytes: int = 64 * 1024,
    allow_exact_event_routes: bool = False,
) -> FlowRouter:
    """Load and warm a production router or fail before serving traffic."""

    registry = WorkflowRegistry.from_yaml(catalog_path)
    calibration = CalibrationConfig.from_yaml(calibration_path)
    manifest = ArtifactManifest.from_yaml(artifact_manifest_path)
    manifest.verify_artifact_path("retriever", retriever_model)
    manifest.verify_artifact_path("verifier", verifier_model)
    retriever = HuggingFaceRetriever(
        str(retriever_model),
        model_version=manifest.retriever_model_version,
        query_prefix=query_prefix,
        document_prefix=document_prefix,
    )
    verifier = HuggingFaceCrossEncoderVerifier(
        str(verifier_model),
        model_version=manifest.verifier_model_version,
    )
    return FlowRouter(
        registry,
        retriever=retriever,
        verifier=verifier,
        calibration=calibration,
        runtime_config=RouterRuntimeConfig.production(
            max_context_bytes=max_context_bytes,
            allow_exact_event_routes=allow_exact_event_routes,
        ),
        artifact_manifest=manifest,
        telemetry=telemetry or LoggingTelemetrySink(),
        top_k=top_k,
    )
