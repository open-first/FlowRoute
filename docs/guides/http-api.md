# HTTP API

The optional FastAPI transport exposes the same typed routing core over HTTP. The CLI command is
intended for local development; production uses explicit settings and an authorization callback.

## Install and run

```bash
pip install "flowroute[api]"
flowroute serve \
  --catalog examples/workflows.yaml \
  --calibration configs/calibration.yaml \
  --host 127.0.0.1 \
  --port 8000
```

## Health

`GET /health` reports lineage and readiness. `GET /health/live` checks only that the process can
respond. `GET /health/ready` returns HTTP 503 when the active production bundle fails its
compatibility check.

```bash
curl -s http://127.0.0.1:8000/health
```

```json
{
  "status": "ok",
  "ready": true,
  "model_version": "tfidf-indexed-word-char-0.2.0+lexical-verifier-0.1.0",
  "calibration_version": "demo-baseline-2026-09-04",
  "catalog_version": "demo-2026-09-04",
  "runtime_mode": "development",
  "generation": 1
}
```

## Route

`POST /v1/route`

```bash
curl -s http://127.0.0.1:8000/v1/route \
  -H 'content-type: application/json' \
  -d '{
    "request_id": "req_901",
    "text": "Cancel my design review tomorrow",
    "context": {"event_id": "evt_123"},
    "catalog_version": "demo-2026-09-04",
    "allowed_workflow_ids": ["calendar.cancel_event"],
    "debug": false
  }'
```

### Request body

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `text` | string | Yes | 1–8,000 characters |
| `request_id` | string or null | No | Generated if absent |
| `context` | object | No | Values used for completeness; validate them again before execution |
| `catalog_version` | string or null | No | Mismatch returns HTTP 409 |
| `allowed_workflow_ids` | string array or null | No | Authorization-derived candidate set |
| `blocked_workflow_ids` | string array | No | Explicit local denylist |
| `event_type` | string or null | No | Exact-event input; ignored by default in production |
| `debug` | boolean | No | Include candidate details |

### Response body

```json
{
  "request_id": "req_901",
  "decision": "ROUTE",
  "workflow_id": "calendar.cancel_event",
  "confidence": 0.91,
  "reason_code": "ACCEPTED_MEDIUM_RISK",
  "missing_inputs": [],
  "confirmation_required": true,
  "model_version": "tfidf-indexed-word-char-0.2.0+lexical-verifier-0.1.0",
  "calibration_version": "demo-baseline-2026-09-04",
  "catalog_version": "demo-2026-09-04",
  "runtime_mode": "development",
  "latency_ms": 4.3,
  "candidates": null
}
```

The numeric values above demonstrate the schema, not guaranteed runtime results.

## Errors

| Status | Cause |
| --- | --- |
| 200 | A typed decision, including abstention, was produced |
| 403 | The authorization callback denied the caller |
| 413 | The request body exceeded the configured limit |
| 409 | Requested `catalog_version` differs from the active version |
| 422 | Request JSON does not satisfy the Pydantic schema |
| 503 | The readiness endpoint detected an invalid active bundle |

An `LLM_REQUIRED` response is not an HTTP error. It is a normal selective-routing decision.

## Production transport requirements

For production, use `ApiSettings.production_defaults(...)` and inject an authorizer as shown in
[Production mode](../operations/production-mode.md). The hardened API adds request limits,
trusted-host enforcement, explicit CORS, request IDs, security headers, and structured access
logs. Keep authentication, distributed rate limits, TLS termination, and global deadlines at your
normal service boundary.
