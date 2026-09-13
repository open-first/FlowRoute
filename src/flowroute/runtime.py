"""Production configuration, artifact compatibility, and atomic router reloads."""

from __future__ import annotations

import hashlib
import re
import threading
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

import yaml
from pydantic import Field, field_validator, model_validator

from .models import RouteRequest, RouteResponse, StrictModel
from .serialization import SERIALIZER_VERSION

if TYPE_CHECKING:
    from .router import FlowRouter

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def sha256_path(path: str | Path) -> str:
    """Hash one file or a directory tree using stable relative paths."""

    target = Path(path)
    if not target.exists():
        raise ProductionConfigurationError(f"artifact path does not exist: {target}")
    digest = hashlib.sha256()
    files = [target] if target.is_file() else sorted(
        item for item in target.rglob("*") if item.is_file()
    )
    if not files:
        raise ProductionConfigurationError(f"artifact path contains no files: {target}")
    for item in files:
        relative = item.name if target.is_file() else item.relative_to(target).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        with item.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()


class RuntimeMode(str, Enum):
    DEVELOPMENT = "development"
    SHADOW = "shadow"
    PRODUCTION = "production"


class RouterRuntimeConfig(StrictModel):
    mode: RuntimeMode = RuntimeMode.DEVELOPMENT
    require_catalog_version: bool = False
    require_workflow_allowlist: bool = False
    allow_exact_event_routes: bool = True
    allow_debug: bool = True
    fail_closed_on_backend_error: bool = False
    max_context_bytes: int = Field(default=64 * 1024, ge=1_024, le=4 * 1024 * 1024)

    @model_validator(mode="after")
    def production_is_fail_closed(self) -> RouterRuntimeConfig:
        if self.mode == RuntimeMode.PRODUCTION:
            unsafe: list[str] = []
            if not self.require_catalog_version:
                unsafe.append("require_catalog_version")
            if not self.require_workflow_allowlist:
                unsafe.append("require_workflow_allowlist")
            if self.allow_debug:
                unsafe.append("allow_debug=false")
            if not self.fail_closed_on_backend_error:
                unsafe.append("fail_closed_on_backend_error")
            if unsafe:
                raise ValueError(
                    "production mode requires fail-closed settings: " + ", ".join(unsafe)
                )
        return self

    @classmethod
    def production(
        cls,
        *,
        max_context_bytes: int = 64 * 1024,
        allow_exact_event_routes: bool = False,
    ) -> RouterRuntimeConfig:
        return cls(
            mode=RuntimeMode.PRODUCTION,
            require_catalog_version=True,
            require_workflow_allowlist=True,
            allow_exact_event_routes=allow_exact_event_routes,
            allow_debug=False,
            fail_closed_on_backend_error=True,
            max_context_bytes=max_context_bytes,
        )

    @classmethod
    def shadow(cls, *, max_context_bytes: int = 64 * 1024) -> RouterRuntimeConfig:
        return cls(
            mode=RuntimeMode.SHADOW,
            require_catalog_version=True,
            require_workflow_allowlist=True,
            allow_exact_event_routes=False,
            allow_debug=True,
            fail_closed_on_backend_error=True,
            max_context_bytes=max_context_bytes,
        )


class ArtifactManifest(StrictModel):
    schema_version: str = Field(default="1", pattern=r"^1$")
    bundle_version: str = Field(min_length=1, max_length=160)
    created_at: datetime
    catalog_version: str = Field(min_length=1, max_length=160)
    catalog_content_hash: str
    serializer_version: str = SERIALIZER_VERSION
    retriever_model_version: str = Field(min_length=1, max_length=500)
    verifier_model_version: str = Field(min_length=1, max_length=500)
    calibration_version: str = Field(min_length=1, max_length=160)
    calibration_content_hash: str
    policy_content_hash: str
    top_k: int = Field(ge=1, le=64)
    retriever_query_prefix: str = Field(default="", max_length=200)
    retriever_document_prefix: str = Field(default="", max_length=200)
    verifier_label_order: tuple[str, str, str] = (
        "mismatch",
        "needs_input",
        "executable",
    )
    allow_exact_event_routes: bool = False
    artifact_hashes: dict[str, str] = Field(min_length=2, max_length=50)
    approved_for_production: bool = False
    approval_reference: str | None = Field(default=None, max_length=500)

    @field_validator(
        "catalog_content_hash",
        "calibration_content_hash",
        "policy_content_hash",
    )
    @classmethod
    def valid_content_hash(cls, value: str) -> str:
        normalized = value.lower()
        if not _SHA256_RE.fullmatch(normalized):
            raise ValueError("must be a lowercase SHA-256 hex digest")
        return normalized

    @field_validator("artifact_hashes")
    @classmethod
    def valid_artifact_hashes(cls, value: dict[str, str]) -> dict[str, str]:
        normalized = {key: digest.lower() for key, digest in value.items()}
        if any(not key.strip() for key in normalized):
            raise ValueError("artifact hash names must not be empty")
        if any(not _SHA256_RE.fullmatch(digest) for digest in normalized.values()):
            raise ValueError("artifact hashes must be SHA-256 hex digests")
        return normalized

    @field_validator("verifier_label_order")
    @classmethod
    def valid_label_order(cls, value: tuple[str, str, str]) -> tuple[str, str, str]:
        expected = {"mismatch", "needs_input", "executable"}
        if set(value) != expected:
            raise ValueError(
                "verifier_label_order must contain mismatch, needs_input, and executable"
            )
        return value

    @model_validator(mode="after")
    def valid_approval(self) -> ArtifactManifest:
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must include a timezone")
        if self.approved_for_production and not self.approval_reference:
            raise ValueError("production approval requires approval_reference")
        if self.approved_for_production:
            missing = {"retriever", "verifier"} - set(self.artifact_hashes)
            if missing:
                raise ValueError(
                    "production approval requires artifact hashes for: "
                    + ", ".join(sorted(missing))
                )
        return self

    @classmethod
    def from_yaml(cls, path: str | Path) -> ArtifactManifest:
        with Path(path).open("r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle)
        if not isinstance(raw, dict):
            raise ValueError("artifact manifest YAML root must be an object")
        return cls.model_validate(raw)

    def verify_compatibility(
        self,
        *,
        catalog_version: str,
        catalog_content_hash: str,
        retriever_model_version: str,
        verifier_model_version: str,
        calibration_version: str,
        calibration_content_hash: str,
        policy_content_hash: str,
        top_k: int,
        retriever_query_prefix: str,
        retriever_document_prefix: str,
        verifier_label_order: tuple[str, str, str],
        allow_exact_event_routes: bool,
        require_approval: bool,
    ) -> None:
        expected = {
            "catalog_version": catalog_version,
            "catalog_content_hash": catalog_content_hash,
            "serializer_version": SERIALIZER_VERSION,
            "retriever_model_version": retriever_model_version,
            "verifier_model_version": verifier_model_version,
            "calibration_version": calibration_version,
            "calibration_content_hash": calibration_content_hash,
            "policy_content_hash": policy_content_hash,
            "top_k": top_k,
            "retriever_query_prefix": retriever_query_prefix,
            "retriever_document_prefix": retriever_document_prefix,
            "verifier_label_order": verifier_label_order,
            "allow_exact_event_routes": allow_exact_event_routes,
        }
        actual = {key: getattr(self, key) for key in expected}
        mismatches = [
            f"{key}: manifest={actual[key]!r}, runtime={value!r}"
            for key, value in expected.items()
            if actual[key] != value
        ]
        if mismatches:
            raise ProductionConfigurationError(
                "artifact bundle is incompatible: " + "; ".join(mismatches)
            )
        if require_approval and not self.approved_for_production:
            raise ProductionConfigurationError(
                "artifact bundle is not approved for production"
            )

    def verify_artifact_path(self, name: str, path: str | Path) -> None:
        expected = self.artifact_hashes.get(name)
        if expected is None:
            raise ProductionConfigurationError(
                f"artifact manifest has no hash for {name!r}"
            )
        actual = sha256_path(path)
        if actual != expected:
            raise ProductionConfigurationError(
                f"{name} artifact hash does not match the manifest"
            )


class ProductionConfigurationError(ValueError):
    pass


class RuntimeGenerationError(RuntimeError):
    pass


class RuntimeSnapshot(StrictModel):
    generation: int = Field(ge=1)
    loaded_at: datetime
    ready: bool
    runtime_mode: RuntimeMode
    model_version: str
    calibration_version: str
    catalog_version: str
    catalog_content_hash: str
    bundle_version: str | None = None


class RouterRuntime:
    """Atomically swap complete, prevalidated router bundles.

    In-flight calls retain their old router object. New calls observe the new
    bundle after one lock-protected pointer swap.
    """

    def __init__(self, router: FlowRouter) -> None:
        self._lock = threading.RLock()
        self._router = router
        self._previous: FlowRouter | None = None
        self._generation = 1
        self._loaded_at = datetime.now(timezone.utc)

    @property
    def current(self) -> FlowRouter:
        with self._lock:
            return self._router

    def route(self, request: RouteRequest) -> RouteResponse:
        with self._lock:
            router = self._router
        return router.route(request)

    def snapshot(self) -> RuntimeSnapshot:
        with self._lock:
            router = self._router
            manifest = router.artifact_manifest
            return RuntimeSnapshot(
                generation=self._generation,
                loaded_at=self._loaded_at,
                ready=router.is_ready(),
                runtime_mode=router.runtime_config.mode,
                model_version=router.model_version,
                calibration_version=router.calibration.version,
                catalog_version=router.registry.catalog_version,
                catalog_content_hash=router.registry.content_hash,
                bundle_version=manifest.bundle_version if manifest else None,
            )

    def replace(
        self,
        router: FlowRouter,
        *,
        expected_generation: int | None = None,
    ) -> RuntimeSnapshot:
        with self._lock:
            self._require_generation(expected_generation)
            if router.runtime_config.mode != self._router.runtime_config.mode:
                raise ProductionConfigurationError(
                    "atomic reload cannot change the runtime mode"
                )
            self._previous = self._router
            self._router = router
            self._generation += 1
            self._loaded_at = datetime.now(timezone.utc)
            return self.snapshot()

    def rollback(self, *, expected_generation: int | None = None) -> RuntimeSnapshot:
        with self._lock:
            self._require_generation(expected_generation)
            if self._previous is None:
                raise RuntimeGenerationError("no previous router bundle is available")
            self._router, self._previous = self._previous, self._router
            self._generation += 1
            self._loaded_at = datetime.now(timezone.utc)
            return self.snapshot()

    def _require_generation(self, expected_generation: int | None) -> None:
        if expected_generation is not None and expected_generation != self._generation:
            raise RuntimeGenerationError(
                f"expected generation {expected_generation}, active generation is "
                f"{self._generation}"
            )
