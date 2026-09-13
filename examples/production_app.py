"""Environment-driven production ASGI entrypoint.

The authorization callback is application-owned and must return the workflow
IDs available to the authenticated caller.
"""

from __future__ import annotations

import importlib
import os
from collections.abc import Callable

from flowroute import LoggingTelemetrySink, load_production_router
from flowroute.api import ApiSettings, create_app


def required_environment(name: str) -> str:
    value = os.environ.get(name)
    if value is None or not value.strip():
        raise RuntimeError(f"missing required environment variable: {name}")
    return value.strip()


def environment_list(name: str, *, required: bool = False) -> list[str]:
    raw = required_environment(name) if required else os.environ.get(name, "")
    return [item.strip() for item in raw.split(",") if item.strip()]


def environment_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc


def load_authorizer(specification: str) -> Callable:
    module_name, separator, attribute = specification.partition(":")
    if not separator or not module_name or not attribute:
        raise RuntimeError(
            "FLOWROUTE_AUTHORIZER must use the format module.path:callable"
        )
    callback = getattr(importlib.import_module(module_name), attribute, None)
    if not callable(callback):
        raise RuntimeError(f"authorization callback is not callable: {specification}")
    return callback


router = load_production_router(
    catalog_path=required_environment("FLOWROUTE_CATALOG"),
    calibration_path=required_environment("FLOWROUTE_CALIBRATION"),
    artifact_manifest_path=required_environment("FLOWROUTE_ARTIFACT_MANIFEST"),
    retriever_model=required_environment("FLOWROUTE_RETRIEVER_MODEL"),
    verifier_model=required_environment("FLOWROUTE_VERIFIER_MODEL"),
    query_prefix=os.environ.get("FLOWROUTE_QUERY_PREFIX", ""),
    document_prefix=os.environ.get("FLOWROUTE_DOCUMENT_PREFIX", ""),
    top_k=environment_int("FLOWROUTE_TOP_K", 8),
    max_context_bytes=environment_int("FLOWROUTE_MAX_CONTEXT_BYTES", 64 * 1024),
    telemetry=LoggingTelemetrySink(),
)

settings = ApiSettings.production_defaults(
    trusted_hosts=environment_list("FLOWROUTE_TRUSTED_HOSTS", required=True),
    cors_origins=environment_list("FLOWROUTE_CORS_ORIGINS"),
    max_body_bytes=environment_int("FLOWROUTE_MAX_BODY_BYTES", 128 * 1024),
)

app = create_app(
    router,
    authorizer=load_authorizer(required_environment("FLOWROUTE_AUTHORIZER")),
    settings=settings,
)
