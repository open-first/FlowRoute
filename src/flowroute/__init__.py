"""FlowRoute public API."""

from .calibration import CalibrationConfig, TierThreshold
from .factory import load_production_router
from .models import (
    CandidateScore,
    CatalogSnapshot,
    Decision,
    InputSpec,
    RetrievalHit,
    RiskTier,
    RouteRequest,
    RouteResponse,
    SideEffect,
    VerificationLabel,
    WorkflowContract,
)
from .registry import WorkflowRegistry
from .router import FlowRouter
from .runtime import (
    ArtifactManifest,
    ProductionConfigurationError,
    RouterRuntime,
    RouterRuntimeConfig,
    RuntimeGenerationError,
    RuntimeMode,
    RuntimeSnapshot,
    sha256_path,
)
from .telemetry import (
    CallbackTelemetrySink,
    InMemoryTelemetrySink,
    LoggingTelemetrySink,
)

__all__ = [
    "CalibrationConfig",
    "CandidateScore",
    "CatalogSnapshot",
    "CallbackTelemetrySink",
    "Decision",
    "FlowRouter",
    "InputSpec",
    "InMemoryTelemetrySink",
    "LoggingTelemetrySink",
    "load_production_router",
    "ArtifactManifest",
    "ProductionConfigurationError",
    "RiskTier",
    "RouteRequest",
    "RouteResponse",
    "RetrievalHit",
    "RouterRuntime",
    "RouterRuntimeConfig",
    "RuntimeGenerationError",
    "RuntimeMode",
    "RuntimeSnapshot",
    "sha256_path",
    "SideEffect",
    "TierThreshold",
    "VerificationLabel",
    "WorkflowContract",
    "WorkflowRegistry",
]

__version__ = "0.2.0"
