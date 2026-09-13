"""Safe orchestration of deterministic policy, retrieval, verification, and abstention."""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import cast

from .calibration import CalibrationConfig
from .inputs import resolve_required_inputs
from .models import (
    CandidateScore,
    Decision,
    RouteRequest,
    RouteResponse,
    VerificationLabel,
    WorkflowContract,
)
from .policy import RoutingPolicy, confirmation_required
from .registry import WorkflowRegistry
from .retrieval import Retriever, TfidfRetriever
from .runtime import (
    ArtifactManifest,
    ProductionConfigurationError,
    RouterRuntimeConfig,
    RuntimeMode,
)
from .telemetry import LoggingTelemetrySink, NullTelemetrySink, TelemetrySink
from .verification import LexicalVerifier, Verifier

_LOGGER = logging.getLogger("flowroute")


class FlowRouter:
    def __init__(
        self,
        registry: WorkflowRegistry,
        *,
        retriever: Retriever | None = None,
        verifier: Verifier | None = None,
        calibration: CalibrationConfig | None = None,
        policy: RoutingPolicy | None = None,
        runtime_config: RouterRuntimeConfig | None = None,
        artifact_manifest: ArtifactManifest | None = None,
        telemetry: TelemetrySink | None = None,
        top_k: int = 8,
    ) -> None:
        if not 1 <= top_k <= 64:
            raise ValueError("top_k must be between 1 and 64")
        self.registry = registry
        self.retriever = retriever or TfidfRetriever()
        self.verifier = verifier or LexicalVerifier()
        self.calibration = calibration or CalibrationConfig()
        self.policy = policy or RoutingPolicy()
        self.runtime_config = runtime_config or RouterRuntimeConfig()
        self.artifact_manifest = artifact_manifest
        if telemetry is not None:
            self.telemetry = telemetry
        elif self.runtime_config.mode == RuntimeMode.PRODUCTION:
            self.telemetry = LoggingTelemetrySink()
        else:
            self.telemetry = NullTelemetrySink()
        self.top_k = top_k
        self._validate_runtime_bundle()
        prepare = getattr(self.retriever, "prepare", None)
        if callable(prepare):
            prepare(self.registry.active_workflows())

    @property
    def model_version(self) -> str:
        return f"{self.retriever.model_version}+{self.verifier.model_version}"

    def is_ready(self) -> bool:
        if self.runtime_config.mode != RuntimeMode.PRODUCTION:
            return True
        try:
            self._verify_artifact_compatibility(require_approval=True)
        except ProductionConfigurationError:
            return False
        return True

    def _validate_runtime_bundle(self) -> None:
        production = self.runtime_config.mode == RuntimeMode.PRODUCTION
        if production:
            if not getattr(self.retriever, "production_capable", False):
                raise ProductionConfigurationError(
                    "production mode requires a production-capable retriever"
                )
            if not getattr(self.verifier, "production_capable", False):
                raise ProductionConfigurationError(
                    "production mode requires a production-capable verifier"
                )
            issues = self.registry.production_issues()
            if issues:
                raise ProductionConfigurationError(
                    "catalog is not production-ready: " + "; ".join(issues)
                )
            if self.artifact_manifest is None:
                raise ProductionConfigurationError(
                    "production mode requires an artifact manifest"
                )
        if self.artifact_manifest is not None:
            self._verify_artifact_compatibility(require_approval=production)

    def _verify_artifact_compatibility(self, *, require_approval: bool) -> None:
        manifest = self.artifact_manifest
        if manifest is None:
            raise ProductionConfigurationError("artifact manifest is not loaded")
        verifier_label_order = cast(
            tuple[str, str, str],
            tuple(
                item.value if hasattr(item, "value") else str(item)
                for item in getattr(
                    self.verifier,
                    "label_order",
                    ("mismatch", "needs_input", "executable"),
                )
            ),
        )
        manifest.verify_compatibility(
            catalog_version=self.registry.catalog_version,
            catalog_content_hash=self.registry.content_hash,
            retriever_model_version=self.retriever.model_version,
            verifier_model_version=self.verifier.model_version,
            calibration_version=self.calibration.version,
            calibration_content_hash=self.calibration.content_hash,
            policy_content_hash=self.policy.content_hash,
            top_k=self.top_k,
            retriever_query_prefix=getattr(self.retriever, "query_prefix", ""),
            retriever_document_prefix=getattr(self.retriever, "document_prefix", ""),
            verifier_label_order=verifier_label_order,
            allow_exact_event_routes=self.runtime_config.allow_exact_event_routes,
            require_approval=require_approval,
        )

    def _backend_failure(
        self,
        *,
        started: float,
        request_id: str,
        stage: str,
        error: Exception | None = None,
    ) -> RouteResponse:
        if not self.runtime_config.fail_closed_on_backend_error:
            if error is not None:
                raise error
            raise RuntimeError(f"{stage} backend returned an invalid response")
        if error is not None:
            _LOGGER.exception("%s backend failed", stage, exc_info=error)
        else:
            _LOGGER.error("%s backend returned an invalid response", stage)
        return self._response(
            started,
            request_id,
            Decision.LLM_REQUIRED,
            "BACKEND_UNAVAILABLE",
        )

    def _response(
        self,
        started: float,
        request_id: str,
        decision: Decision,
        reason_code: str,
        *,
        workflow: WorkflowContract | None = None,
        confidence: float = 0.0,
        missing_inputs: list[str] | None = None,
        candidates: list[CandidateScore] | None = None,
        debug: bool = False,
    ) -> RouteResponse:
        manifest = self.artifact_manifest
        response = RouteResponse(
            request_id=request_id,
            decision=decision,
            workflow_id=workflow.id if workflow else None,
            confidence=round(float(confidence), 6),
            reason_code=reason_code,
            missing_inputs=missing_inputs or [],
            confirmation_required=confirmation_required(workflow) if workflow else False,
            model_version=(
                f"{manifest.retriever_model_version}+{manifest.verifier_model_version}"
                if manifest
                else self.model_version
            ),
            calibration_version=(
                manifest.calibration_version if manifest else self.calibration.version
            ),
            catalog_version=(
                manifest.catalog_version if manifest else self.registry.catalog_version
            ),
            runtime_mode=self.runtime_config.mode.value,
            latency_ms=round((time.perf_counter() - started) * 1_000, 3),
            candidates=candidates if debug else None,
        )
        try:
            self.telemetry.record(response)
        except Exception:
            _LOGGER.exception("routing telemetry sink failed")
        return response

    def route(self, request: RouteRequest) -> RouteResponse:
        started = time.perf_counter()
        request_id = request.request_id or f"req_{uuid.uuid4().hex}"
        if self.runtime_config.mode == RuntimeMode.PRODUCTION:
            try:
                self._verify_artifact_compatibility(require_approval=True)
            except ProductionConfigurationError:
                _LOGGER.exception("active routing bundle failed its integrity check")
                return self._response(
                    started,
                    request_id,
                    Decision.LLM_REQUIRED,
                    "RUNTIME_INTEGRITY_FAILURE",
                )
        if self.runtime_config.require_catalog_version and request.catalog_version is None:
            return self._response(
                started,
                request_id,
                Decision.LLM_REQUIRED,
                "CATALOG_VERSION_REQUIRED",
            )
        self.registry.require_version(request.catalog_version)
        if (
            self.runtime_config.require_workflow_allowlist
            and request.allowed_workflow_ids is None
        ):
            return self._response(
                started,
                request_id,
                Decision.LLM_REQUIRED,
                "WORKFLOW_ALLOWLIST_REQUIRED",
            )
        if request.debug and not self.runtime_config.allow_debug:
            return self._response(
                started,
                request_id,
                Decision.LLM_REQUIRED,
                "DEBUG_DISABLED",
            )
        try:
            serialized_context = json.dumps(
                request.context,
                allow_nan=False,
                separators=(",", ":"),
            )
        except (TypeError, ValueError, RuntimeError, RecursionError):
            return self._response(
                started,
                request_id,
                Decision.LLM_REQUIRED,
                "INVALID_CONTEXT",
            )
        context_bytes = len(serialized_context.encode("utf-8"))
        if context_bytes > self.runtime_config.max_context_bytes:
            return self._response(
                started,
                request_id,
                Decision.LLM_REQUIRED,
                "CONTEXT_TOO_LARGE",
            )
        request = request.model_copy(
            update={"context": json.loads(serialized_context)}
        )
        candidates = self.policy.filter_candidates(request, self.registry.active_workflows())
        if not candidates:
            return self._response(
                started,
                request_id,
                Decision.LLM_REQUIRED,
                "NO_ELIGIBLE_WORKFLOW",
                debug=request.debug,
            )

        if request.event_type and self.runtime_config.allow_exact_event_routes:
            matches = [item for item in candidates if request.event_type in item.event_types]
            if len(matches) > 1:
                return self._response(
                    started,
                    request_id,
                    Decision.LLM_REQUIRED,
                    "AMBIGUOUS_EVENT_RULE",
                    debug=request.debug,
                )
            if len(matches) == 1:
                workflow = matches[0]
                resolution = resolve_required_inputs(workflow, request.text, request.context)
                if resolution.extraction_timeouts:
                    return self._response(
                        started,
                        request_id,
                        Decision.LLM_REQUIRED,
                        "INPUT_EXTRACTION_TIMEOUT",
                        workflow=workflow,
                        debug=request.debug,
                    )
                if resolution.missing:
                    return self._response(
                        started,
                        request_id,
                        Decision.CLARIFY,
                        "EXACT_EVENT_MISSING_INPUT",
                        workflow=workflow,
                        confidence=1.0,
                        missing_inputs=resolution.missing,
                        debug=request.debug,
                    )
                return self._response(
                    started,
                    request_id,
                    Decision.ROUTE,
                    "EXACT_EVENT_RULE",
                    workflow=workflow,
                    confidence=1.0,
                    debug=request.debug,
                )

        guard = self.policy.precheck(request.text)
        if not guard.allow:
            return self._response(
                started, request_id, Decision.LLM_REQUIRED, guard.reason_code, debug=request.debug
            )

        by_id = {item.id: item for item in candidates}
        try:
            hits = self.retriever.rank(request.text, candidates, top_k=self.top_k)
        except Exception as exc:
            return self._backend_failure(
                started=started,
                request_id=request_id,
                stage="retrieval",
                error=exc,
            )
        hit_ids = [hit.workflow_id for hit in hits]
        if (
            len(hit_ids) != len(set(hit_ids))
            or any(workflow_id not in by_id for workflow_id in hit_ids)
        ):
            return self._backend_failure(
                started=started,
                request_id=request_id,
                stage="retrieval",
            )
        if not hits or hits[0].score < self.calibration.min_retrieval_score:
            return self._response(
                started, request_id, Decision.LLM_REQUIRED, "NO_WORKFLOW", debug=request.debug
            )

        pairs = [(by_id[hit.workflow_id], hit) for hit in hits]
        verify_many = getattr(self.verifier, "verify_many", None)
        try:
            if callable(verify_many):
                scored = verify_many(request.text, request.context, pairs)
            else:
                scored = [
                    self.verifier.verify(request.text, request.context, contract, hit)
                    for contract, hit in pairs
                ]
        except Exception as exc:
            return self._backend_failure(
                started=started,
                request_id=request_id,
                stage="verification",
                error=exc,
            )
        scored_ids = [item.workflow_id for item in scored]
        if (
            len(scored) != len(pairs)
            or len(scored_ids) != len(set(scored_ids))
            or set(scored_ids) != set(hit_ids)
        ):
            return self._backend_failure(
                started=started,
                request_id=request_id,
                stage="verification",
            )
        scored.sort(
            key=lambda item: max(item.executable_score, item.needs_input_score), reverse=True
        )
        top = scored[0]
        workflow = by_id[top.workflow_id]
        if any(code.startswith("EXTRACTION_TIMEOUT:") for code in top.reason_codes):
            return self._response(
                started,
                request_id,
                Decision.LLM_REQUIRED,
                "INPUT_EXTRACTION_TIMEOUT",
                workflow=workflow,
                candidates=scored,
                debug=request.debug,
            )
        top_confidence = self.calibration.calibrate(
            max(top.executable_score, top.needs_input_score)
        )
        second_confidence = (
            self.calibration.calibrate(max(scored[1].executable_score, scored[1].needs_input_score))
            if len(scored) > 1
            else 0.0
        )
        margin = top_confidence - second_confidence
        tier = self.calibration.threshold_for(top.risk_tier)

        if margin < tier.margin:
            return self._response(
                started,
                request_id,
                Decision.LLM_REQUIRED,
                "AMBIGUOUS_CANDIDATES",
                confidence=top_confidence,
                candidates=scored,
                debug=request.debug,
            )

        if top.label == VerificationLabel.NEEDS_INPUT:
            if top_confidence >= self.calibration.clarify_threshold:
                return self._response(
                    started,
                    request_id,
                    Decision.CLARIFY,
                    "MISSING_REQUIRED_INPUT",
                    workflow=workflow,
                    confidence=top_confidence,
                    missing_inputs=top.missing_inputs,
                    candidates=scored,
                    debug=request.debug,
                )
            return self._response(
                started,
                request_id,
                Decision.LLM_REQUIRED,
                "LOW_CONFIDENCE_MISSING_INPUT",
                confidence=top_confidence,
                candidates=scored,
                debug=request.debug,
            )

        if top.label != VerificationLabel.EXECUTABLE or top_confidence < tier.route:
            return self._response(
                started,
                request_id,
                Decision.LLM_REQUIRED,
                "BELOW_RISK_THRESHOLD",
                confidence=top_confidence,
                candidates=scored,
                debug=request.debug,
            )

        return self._response(
            started,
            request_id,
            Decision.ROUTE,
            f"ACCEPTED_{top.risk_tier.value.upper()}_RISK",
            workflow=workflow,
            confidence=top_confidence,
            candidates=scored,
            debug=request.debug,
        )
