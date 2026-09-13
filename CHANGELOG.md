# Changelog

## 0.2.0

### Added

- Fail-closed production and shadow runtime modes.
- Approved artifact manifests with compatibility and local checkpoint hash verification.
- Atomic router bundle replacement and rollback with generation guards.
- Authorization callback integration that intersects client and server workflow allowlists.
- Request/context size limits, trusted hosts, explicit CORS, and security headers.
- Liveness, readiness, request-ID propagation, and privacy-conscious structured telemetry.
- Bounded regex extraction and catalog file-size limits.
- Batch verifier interface and production bundle factory.
- Container entrypoint, non-root Dockerfile, and CI workflow.
- Bounded container concurrency, backlog, and keep-alive settings.
- Separate inference and model-training dependency extras.
- CLI commands for bundle inspection and stable artifact hashing.

### Changed

- The TF-IDF development retriever now builds one reusable catalog index.
- Public configuration and contract models are frozen.
- Workflow collection fields use immutable tuples.
- Learned-backend prefixes are neutral and explicitly configurable.

### Safety

- Production mode rejects the lexical development backends.
- Production requests require catalog lineage and an authorization-derived workflow set.
- Exact-event shortcuts are disabled by default in production and bound into the manifest.
- Runtime mutations of routing-relevant artifact settings fail closed.
- Readiness returns HTTP 503 when active artifact integrity fails.
- Backend failures and invalid backend responses fail closed.
- The optional dataset dependency excludes releases affected by a known security advisory.

## 0.1.0

- Initial routing library, CLI, optional API, demo catalog, training scaffold, and documentation.
