# Production mode

FlowRoute 0.2 separates **production-capable infrastructure** from **model quality**.

The service can enforce production safety controls, but it cannot manufacture a validated model.
You must provide trained checkpoints, workflow-disjoint evaluation, calibrated thresholds, and
an approved artifact manifest.

## What production mode enforces

A production `FlowRouter` refuses to start unless:

- the retriever and verifier declare production capability;
- an artifact manifest is supplied and approved;
- catalog, serializer, model, calibration, policy, prefix, label-order, and top-K identities match;
- the exact-event routing policy matches the approved manifest;
- the catalog has owners and no ambiguous exact event mappings; and
- the full workflow index warms successfully.

Each production request must include:

- the active `catalog_version`; and
- an authorization-derived `allowed_workflow_ids` value, including an intentional empty list.

Production mode also disables candidate debugging, limits context size, time-bounds regex
extraction, checks routing-bundle integrity before every request, and converts backend failures
into `LLM_REQUIRED / BACKEND_UNAVAILABLE`.

Exact-event shortcuts are disabled by default in production because an HTTP caller can supply
`event_type`. Enable them only on an authenticated structured-event entrypoint and record the
setting in the artifact manifest.

## Load a production bundle

```python
from flowroute import LoggingTelemetrySink, load_production_router

router = load_production_router(
    catalog_path="/config/workflows.yaml",
    calibration_path="/config/calibration.yaml",
    artifact_manifest_path="/config/artifact-manifest.yaml",
    retriever_model="/models/retriever",
    verifier_model="/models/verifier",
    telemetry=LoggingTelemetrySink(),
    top_k=8,
    allow_exact_event_routes=False,
)
```

The production factory requires local model paths and verifies their complete directory hashes
before loading them. This avoids depending on a mutable remote model identifier during startup.

## Inject authorization

The HTTP service never trusts the client's requested workflow IDs as authorization.

```python
from flowroute.api import ApiSettings, AuthorizationDenied, create_app

async def authorize(request, payload):
    principal = request.scope.get("authenticated_principal")
    if principal is None:
        raise AuthorizationDenied()

    return await permission_service.allowed_workflow_ids(principal)

settings = ApiSettings.production_defaults(
    trusted_hosts=["router.example.internal"],
    cors_origins=[],
)

app = create_app(
    router,
    authorizer=authorize,
    settings=settings,
)
```

If the client also supplies an allowlist, FlowRoute uses the intersection of the client list and
the authorization callback result. The client can narrow access but cannot expand it.

## Atomic reload

`RouterRuntime` swaps complete, already-validated router objects:

```python
from flowroute import RouterRuntime

runtime = RouterRuntime(router)
before = runtime.snapshot()

new_router = load_production_router(
    catalog_path="/config/workflows-v2.yaml",
    calibration_path="/config/calibration-v2.yaml",
    artifact_manifest_path="/config/artifact-manifest-v2.yaml",
    retriever_model="/models/retriever-v2",
    verifier_model="/models/verifier-v2",
)

after = runtime.replace(
    new_router,
    expected_generation=before.generation,
)
```

In-flight requests retain the old object. New requests see the new generation after one
lock-protected pointer swap. Reload cannot change the runtime mode.

Rollback keeps the previous bundle:

```python
runtime.rollback(expected_generation=after.generation)
```

## Service controls

The production API provides:

- `GET /health/live`;
- `GET /health/ready`;
- `POST /v1/route`;
- request-body limits;
- validated or generated request IDs;
- trusted-host enforcement;
- explicit CORS only;
- disabled interactive API docs;
- no-store and basic hardening headers;
- privacy-conscious structured access logs; and
- CPU inference outside the async event loop.

The readiness endpoint returns HTTP 503 if the active production bundle no longer matches its
manifest. Liveness remains independent so an orchestrator can distinguish a running process from
a safe traffic target.

Use an ingress or service mesh for distributed rate limiting, TLS, global deadlines, and
authentication. In-process rate limits are inconsistent across workers and replicas.
