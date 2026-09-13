"""Typed public contracts for FlowRoute."""

from __future__ import annotations

import json
import re
from collections import Counter
from enum import Enum
from typing import Any

import regex
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

WORKFLOW_ID_RE = re.compile(r"^[a-z][a-z0-9_.-]{2,127}$")
SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:[-+][0-9A-Za-z.-]+)?$")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=True)


class Decision(str, Enum):
    ROUTE = "ROUTE"
    CLARIFY = "CLARIFY"
    LLM_REQUIRED = "LLM_REQUIRED"


class VerificationLabel(str, Enum):
    EXECUTABLE = "executable"
    NEEDS_INPUT = "needs_input"
    MISMATCH = "mismatch"


class RiskTier(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SideEffect(str, Enum):
    READ_ONLY = "read_only"
    INTERNAL_WRITE = "internal_write"
    EXTERNAL_WRITE = "external_write"
    DESTRUCTIVE = "destructive"


class WorkflowStatus(str, Enum):
    ACTIVE = "active"
    DISABLED = "disabled"
    DEPRECATED = "deprecated"


class InputSpec(StrictModel):
    """One input needed by a workflow.

    ``pattern`` is optional and only extracts a value from user text. Trusted
    structured context always takes precedence over text extraction.
    """

    name: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_]*$")
    description: str = Field(default="", max_length=500)
    aliases: tuple[str, ...] = Field(default_factory=tuple, max_length=20)
    pattern: str | None = Field(default=None, max_length=500)

    @field_validator("pattern")
    @classmethod
    def valid_pattern(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                regex.compile(value, flags=regex.IGNORECASE)
            except regex.error as exc:
                raise ValueError(f"invalid extraction regex: {exc}") from exc
        return value


class WorkflowContract(StrictModel):
    id: str = Field(min_length=3, max_length=128)
    version: str
    name: str = Field(min_length=3, max_length=160)
    description: str = Field(min_length=10, max_length=2_000)
    positive_capabilities: tuple[str, ...] = Field(default_factory=tuple, max_length=30)
    exclusions: tuple[str, ...] = Field(default_factory=tuple, max_length=30)
    required_inputs: tuple[InputSpec, ...] = Field(default_factory=tuple, max_length=30)
    optional_inputs: tuple[InputSpec, ...] = Field(default_factory=tuple, max_length=30)
    preconditions: tuple[str, ...] = Field(default_factory=tuple, max_length=30)
    side_effect: SideEffect = SideEffect.READ_ONLY
    risk_tier: RiskTier = RiskTier.LOW
    confirmation: str = Field(default="never", min_length=3, max_length=100)
    examples: tuple[str, ...] = Field(default_factory=tuple, max_length=50)
    event_types: tuple[str, ...] = Field(default_factory=tuple, max_length=30)
    owner: str = Field(default="unknown", min_length=1, max_length=160)
    status: WorkflowStatus = WorkflowStatus.ACTIVE
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def serializable_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        _require_json_object(value, "workflow metadata")
        return value

    @field_validator("id")
    @classmethod
    def valid_id(cls, value: str) -> str:
        if not WORKFLOW_ID_RE.fullmatch(value):
            raise ValueError("must be a lowercase namespaced identifier")
        return value

    @field_validator("version")
    @classmethod
    def valid_version(cls, value: str) -> str:
        if not SEMVER_RE.fullmatch(value):
            raise ValueError("must be semantic versioning, for example 1.0.0")
        return value

    @field_validator("required_inputs", "optional_inputs", mode="before")
    @classmethod
    def expand_input_shorthand(cls, value: Any) -> Any:
        if value is None:
            return []
        return [{"name": item} if isinstance(item, str) else item for item in value]

    @model_validator(mode="after")
    def validate_safety_fields(self) -> WorkflowContract:
        names = [item.name for item in self.required_inputs + self.optional_inputs]
        if len(names) != len(set(names)):
            raise ValueError("input names must be unique across required and optional inputs")
        if self.side_effect in {SideEffect.EXTERNAL_WRITE, SideEffect.DESTRUCTIVE}:
            if not self.exclusions:
                raise ValueError("external or destructive workflows must declare exclusions")
            if self.confirmation == "never":
                raise ValueError(
                    "external or destructive workflows must declare a confirmation policy"
                )
        return self


class CatalogSnapshot(StrictModel):
    catalog_version: str = Field(min_length=1, max_length=160)
    workflows: tuple[WorkflowContract, ...] = Field(min_length=1, max_length=50_000)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def serializable_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        _require_json_object(value, "catalog metadata")
        return value

    @model_validator(mode="after")
    def unique_workflow_ids(self) -> CatalogSnapshot:
        active_ids = [item.id for item in self.workflows if item.status == WorkflowStatus.ACTIVE]
        duplicates = sorted(item for item, count in Counter(active_ids).items() if count > 1)
        if duplicates:
            raise ValueError(f"duplicate active workflow ids: {', '.join(duplicates)}")
        return self


class RouteRequest(StrictModel):
    request_id: str | None = Field(
        default=None,
        max_length=160,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$",
    )
    text: str = Field(min_length=1, max_length=8_000)
    context: dict[str, Any] = Field(default_factory=dict)
    catalog_version: str | None = Field(default=None, max_length=160)
    allowed_workflow_ids: tuple[str, ...] | None = Field(default=None, max_length=50_000)
    blocked_workflow_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=50_000)
    event_type: str | None = Field(
        default=None,
        max_length=160,
        pattern=r"^[A-Za-z][A-Za-z0-9_.:-]*$",
    )
    debug: bool = False

    @field_validator("context")
    @classmethod
    def serializable_context(cls, value: dict[str, Any]) -> dict[str, Any]:
        _require_json_object(value, "request context")
        return value

    @field_validator("allowed_workflow_ids", "blocked_workflow_ids")
    @classmethod
    def unique_workflow_lists(
        cls, value: tuple[str, ...] | None
    ) -> tuple[str, ...] | None:
        if value is not None and len(value) != len(set(value)):
            raise ValueError("workflow id lists must not contain duplicates")
        if value is not None and any(not WORKFLOW_ID_RE.fullmatch(item) for item in value):
            raise ValueError("workflow id lists contain an invalid workflow ID")
        return value


class RetrievalHit(StrictModel):
    workflow_id: str
    score: float = Field(ge=0.0, le=1.0)
    rank: int = Field(ge=1)


class CandidateScore(StrictModel):
    workflow_id: str
    risk_tier: RiskTier
    retrieval_score: float = Field(ge=0.0, le=1.0)
    executable_score: float = Field(ge=0.0, le=1.0)
    needs_input_score: float = Field(ge=0.0, le=1.0)
    mismatch_score: float = Field(ge=0.0, le=1.0)
    label: VerificationLabel
    missing_inputs: list[str] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)


class RouteResponse(StrictModel):
    request_id: str
    decision: Decision
    workflow_id: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    reason_code: str
    missing_inputs: list[str] = Field(default_factory=list)
    confirmation_required: bool = False
    model_version: str
    calibration_version: str
    catalog_version: str
    runtime_mode: str = "development"
    latency_ms: float = Field(ge=0.0)
    candidates: list[CandidateScore] | None = None


class HealthResponse(StrictModel):
    status: str
    ready: bool = True
    model_version: str
    catalog_version: str
    calibration_version: str = "unknown"
    runtime_mode: str = "development"
    generation: int = Field(default=1, ge=1)


def _require_json_object(value: dict[str, Any], label: str) -> None:
    try:
        json.dumps(value, allow_nan=False, separators=(",", ":"))
    except (TypeError, ValueError, RecursionError) as exc:
        raise ValueError(f"{label} must contain only finite JSON values") from exc
