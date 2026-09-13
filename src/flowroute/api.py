"""Optional hardened FastAPI transport."""

from __future__ import annotations

import inspect
import json
import logging
import re
import time
import uuid
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from pydantic import Field, field_validator, model_validator

from .models import HealthResponse, RouteRequest, RouteResponse, StrictModel
from .registry import CatalogVersionError
from .router import FlowRouter
from .runtime import ProductionConfigurationError, RouterRuntime, RuntimeMode

try:
    from starlette.requests import Request
except ImportError:
    Request = Any  # type: ignore[misc,assignment]

_LOGGER = logging.getLogger("flowroute.api")
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}$")

Authorizer = Callable[
    [Any, RouteRequest],
    Sequence[str] | Awaitable[Sequence[str]],
]


class AuthorizationDenied(PermissionError):
    pass


class ApiSettings(StrictModel):
    production: bool = False
    max_body_bytes: int = Field(default=128 * 1024, ge=1_024, le=8 * 1024 * 1024)
    trusted_hosts: tuple[str, ...] = Field(default=("*",), min_length=1, max_length=100)
    cors_origins: tuple[str, ...] = Field(default_factory=tuple, max_length=100)
    docs_enabled: bool = True
    require_authorizer: bool = False

    @field_validator("trusted_hosts")
    @classmethod
    def valid_trusted_hosts(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        for host in values:
            if not host:
                raise ValueError("trusted host names must not be empty")
            if any(character.isspace() for character in host):
                raise ValueError("trusted host names must not contain whitespace")
            if "://" in host or "/" in host or "," in host:
                raise ValueError("trusted hosts must be host names, not URLs")
            if "*" in host and (
                host != "*" and (not host.startswith("*.") or host.count("*") != 1)
            ):
                raise ValueError("host wildcards are only allowed as a leading '*.'")
        return values

    @field_validator("cors_origins")
    @classmethod
    def valid_cors_origins(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        origin_pattern = re.compile(
            r"^https?://(?:\[[0-9A-Fa-f:]+\]|[^/@\s:?#]+)(?::\d{1,5})?$"
        )
        for origin in values:
            if origin != "*" and not origin_pattern.fullmatch(origin):
                raise ValueError(
                    "CORS origins must be '*' or an HTTP(S) origin without a path"
                )
            if origin.rsplit(":", 1)[-1].isdigit():
                port = int(origin.rsplit(":", 1)[-1])
                if port > 65_535:
                    raise ValueError("CORS origin port must be at most 65535")
        return values

    @model_validator(mode="after")
    def production_is_explicit(self) -> ApiSettings:
        if self.production:
            problems: list[str] = []
            if "*" in self.trusted_hosts:
                problems.append("trusted_hosts cannot contain '*'")
            if "*" in self.cors_origins:
                problems.append("cors_origins cannot contain '*'")
            if self.docs_enabled:
                problems.append("docs_enabled must be false")
            if not self.require_authorizer:
                problems.append("require_authorizer must be true")
            if problems:
                raise ValueError(
                    "unsafe production API settings: " + ", ".join(problems)
                )
        return self

    @classmethod
    def production_defaults(
        cls,
        *,
        trusted_hosts: Sequence[str],
        cors_origins: Sequence[str] | None = None,
        max_body_bytes: int = 128 * 1024,
    ) -> ApiSettings:
        return cls(
            production=True,
            max_body_bytes=max_body_bytes,
            trusted_hosts=tuple(trusted_hosts),
            cors_origins=tuple(cors_origins or ()),
            docs_enabled=False,
            require_authorizer=True,
        )


def _request_id(value: str | None) -> str:
    if value and _REQUEST_ID_RE.fullmatch(value):
        return value
    return f"req_{uuid.uuid4().hex}"


def _intersect_authorization(
    authorized: Sequence[str],
    requested: Sequence[str] | None,
) -> list[str]:
    if isinstance(authorized, (str, bytes)):
        raise TypeError("authorizer must return a sequence of workflow IDs")
    if len(authorized) > 50_000:
        raise ValueError("authorizer returned too many workflow IDs")
    unique_authorized = list(dict.fromkeys(authorized))
    if any(not isinstance(item, str) for item in unique_authorized):
        raise TypeError("authorizer returned a non-string workflow ID")
    if requested is None:
        return unique_authorized
    requested_set = set(requested)
    return [item for item in unique_authorized if item in requested_set]


def create_app(
    router: FlowRouter | RouterRuntime,
    *,
    authorizer: Authorizer | None = None,
    settings: ApiSettings | None = None,
):
    try:
        from fastapi import FastAPI, HTTPException
        from fastapi.middleware.cors import CORSMiddleware
        from fastapi.responses import JSONResponse
        from starlette.concurrency import run_in_threadpool
        from starlette.middleware.trustedhost import TrustedHostMiddleware
    except ImportError as exc:
        raise RuntimeError('API support requires: pip install -e ".[api]"') from exc

    runtime = router if isinstance(router, RouterRuntime) else RouterRuntime(router)
    router_is_production = runtime.current.runtime_config.mode == RuntimeMode.PRODUCTION
    if router_is_production and settings is None:
        raise ProductionConfigurationError(
            "production router requires explicit production ApiSettings"
        )
    settings = settings or ApiSettings()
    if router_is_production and not settings.production:
        raise ProductionConfigurationError(
            "production router cannot use development API settings"
        )
    if settings.require_authorizer and authorizer is None:
        raise ProductionConfigurationError(
            "API settings require an authorization callback"
        )

    docs_url = "/docs" if settings.docs_enabled else None
    openapi_url = "/openapi.json" if settings.docs_enabled else None
    app = FastAPI(
        title="FlowRoute",
        version="0.2.0",
        description="Selective routing to deterministic workflows without generative inference.",
        docs_url=docs_url,
        redoc_url=None,
        openapi_url=openapi_url,
    )
    app.state.flowroute_runtime = runtime

    if settings.trusted_hosts != ("*",):
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST"],
            allow_headers=["authorization", "content-type", "x-request-id"],
        )

    @app.middleware("http")
    async def request_guard(request: Request, call_next):
        started = time.perf_counter()
        request.state.request_id = _request_id(request.headers.get("x-request-id"))
        response = None

        def request_too_large_response():
            return JSONResponse(
                status_code=413,
                content={
                    "error": "REQUEST_TOO_LARGE",
                    "request_id": request.state.request_id,
                },
            )

        content_length = request.headers.get("content-length")
        if content_length:
            try:
                declared_size = int(content_length)
            except ValueError:
                declared_size = settings.max_body_bytes + 1
            if declared_size > settings.max_body_bytes:
                response = request_too_large_response()
        if response is None and request.method in {"POST", "PUT", "PATCH"}:
            chunks: list[bytes] = []
            received_size = 0
            async for chunk in request.stream():
                received_size += len(chunk)
                if received_size > settings.max_body_bytes:
                    response = request_too_large_response()
                    break
                chunks.append(chunk)
            if response is None:
                request._body = b"".join(chunks)
        if response is None:
            response = await call_next(request)
        response.headers["x-request-id"] = request.state.request_id
        response.headers["x-content-type-options"] = "nosniff"
        response.headers["x-frame-options"] = "DENY"
        response.headers["cache-control"] = "no-store"
        event = {
            "event": "flowroute.http",
            "request_id": request.state.request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "latency_ms": round((time.perf_counter() - started) * 1_000, 3),
        }
        _LOGGER.info(json.dumps(event, sort_keys=True, separators=(",", ":")))
        return response

    def health_response() -> HealthResponse:
        snapshot = runtime.snapshot()
        return HealthResponse(
            status="ok" if snapshot.ready else "not_ready",
            ready=snapshot.ready,
            model_version=snapshot.model_version,
            calibration_version=snapshot.calibration_version,
            catalog_version=snapshot.catalog_version,
            runtime_mode=snapshot.runtime_mode,
            generation=snapshot.generation,
        )

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return health_response()

    @app.get("/health/live", response_model=dict[str, str])
    def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready", response_model=HealthResponse)
    def ready():
        response = health_response()
        if not response.ready:
            return JSONResponse(
                status_code=503,
                content=response.model_dump(mode="json"),
            )
        return response

    @app.post("/v1/route", response_model=RouteResponse)
    async def route(payload: RouteRequest, request: Request) -> RouteResponse:
        effective = payload
        if payload.request_id is None:
            effective = payload.model_copy(
                update={"request_id": request.state.request_id}
            )
        else:
            request.state.request_id = payload.request_id

        if authorizer is not None:
            try:
                authorization = authorizer(request, effective)
                if inspect.isawaitable(authorization):
                    authorization = await authorization
                effective_ids = _intersect_authorization(
                    authorization,
                    effective.allowed_workflow_ids,
                )
                effective = RouteRequest.model_validate(
                    {
                        **effective.model_dump(mode="python"),
                        "allowed_workflow_ids": effective_ids,
                    }
                )
            except AuthorizationDenied as exc:
                raise HTTPException(
                    status_code=403,
                    detail={
                        "error": "AUTHORIZATION_DENIED",
                        "request_id": request.state.request_id,
                    },
                ) from exc
            except (TypeError, ValueError) as exc:
                _LOGGER.error("authorization callback returned invalid data")
                raise HTTPException(
                    status_code=500,
                    detail={
                        "error": "AUTHORIZATION_INVALID",
                        "request_id": request.state.request_id,
                    },
                ) from exc

        try:
            return await run_in_threadpool(runtime.route, effective)
        except CatalogVersionError as exc:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "CATALOG_VERSION_MISMATCH",
                    "request_id": request.state.request_id,
                },
            ) from exc

    return app
