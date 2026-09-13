# Security policy

## Supported versions

Security fixes are applied to the latest minor release. Older release archives are not maintained.

## Reporting

Do not disclose a suspected vulnerability in a public issue before maintainers have had a
reasonable opportunity to investigate it. Use GitHub's private vulnerability-reporting feature
when available, or email `anorouzi.work@gmail.com` with the subject `FlowRoute security report`.
Include:

- affected version and configuration;
- minimal reproduction;
- expected and observed behavior;
- impact assessment;
- relevant logs with secrets and personal data removed; and
- any suggested mitigation.

## Security boundary

FlowRoute recommends a workflow-specific validation path. It does not authenticate users,
authorize side effects, validate live workflow state, or execute tools.

Production mode requires an application-owned authorization callback and an allowlist on every
request. The downstream orchestrator remains responsible for typed arguments, live preconditions,
confirmation, idempotency, and execution.

## Operational guidance

- Keep catalogs, calibration, manifests, and model directories read-only.
- Pin and hash every deployed artifact.
- Disable debug output for untrusted clients.
- Terminate TLS and enforce distributed rate limits at the ingress.
- Avoid logging raw request text or context.
- Treat model files and serialized indexes as untrusted until their provenance is verified.
