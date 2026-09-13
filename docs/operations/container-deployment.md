# Container deployment

The repository includes a non-root container definition and an environment-driven ASGI entrypoint
at `examples/production_app.py`.

## Build

```bash
docker build -t flowroute:0.2.0 .
```

For a controlled release, pin the Python base image by digest and build from a reviewed dependency
lock generated for the target platform.

## Required environment

| Variable | Meaning |
| --- | --- |
| `FLOWROUTE_CATALOG` | Workflow catalog path |
| `FLOWROUTE_CALIBRATION` | Calibration bundle path |
| `FLOWROUTE_ARTIFACT_MANIFEST` | Approved manifest path |
| `FLOWROUTE_RETRIEVER_MODEL` | Local retriever directory |
| `FLOWROUTE_VERIFIER_MODEL` | Local verifier directory |
| `FLOWROUTE_AUTHORIZER` | Import path such as `your_service.auth:authorize` |
| `FLOWROUTE_TRUSTED_HOSTS` | Comma-separated HTTP hostnames |

Optional variables:

| Variable | Default |
| --- | --- |
| `FLOWROUTE_CORS_ORIGINS` | Empty |
| `FLOWROUTE_QUERY_PREFIX` | Empty |
| `FLOWROUTE_DOCUMENT_PREFIX` | Empty |
| `FLOWROUTE_TOP_K` | `8` |
| `FLOWROUTE_MAX_CONTEXT_BYTES` | `65536` |
| `FLOWROUTE_MAX_BODY_BYTES` | `131072` |

Prefix and top-K values must match the artifact manifest.

## Run

Mount an immutable release directory and your application-owned authorization module:

```bash
docker run --rm -p 8000:8000 \
  -v "$PWD/release/config:/config:ro" \
  -v "$PWD/release/models:/models:ro" \
  -v "$PWD/your_service:/app/your_service:ro" \
  -e FLOWROUTE_CATALOG=/config/workflows.yaml \
  -e FLOWROUTE_CALIBRATION=/config/calibration.yaml \
  -e FLOWROUTE_ARTIFACT_MANIFEST=/config/artifact-manifest.yaml \
  -e FLOWROUTE_RETRIEVER_MODEL=/models/retriever \
  -e FLOWROUTE_VERIFIER_MODEL=/models/verifier \
  -e FLOWROUTE_AUTHORIZER=your_service.auth:authorize \
  -e FLOWROUTE_TRUSTED_HOSTS=localhost \
  flowroute:0.2.0
```

The process runs as UID/GID 10001, uses one worker to avoid silently duplicating model memory,
limits accepted concurrency and backlog, disables duplicate Uvicorn access logs, and checks
`/health/ready`.

## Scaling

Scale with multiple container replicas rather than increasing workers blindly. Each worker loads
its own checkpoints and embedding matrix. Measure memory before changing concurrency.

Put a production ingress in front of the service for:

- TLS termination;
- authentication context;
- distributed rate limiting;
- request deadlines;
- maximum connection counts; and
- load balancing.

Send termination signals with enough grace time for in-flight routing calls to complete.
