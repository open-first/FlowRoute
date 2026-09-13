# Python models

Public models use strict Pydantic validation. Unknown fields are rejected.

## `RouteRequest`

| Field | Type | Default |
| --- | --- | --- |
| `request_id` | `Optional[str]` | `None` |
| `text` | `str` | Required |
| `context` | `dict[str, Any]` | `{}` |
| `catalog_version` | `Optional[str]` | `None` |
| `allowed_workflow_ids` | `Optional[list[str]]` | `None` |
| `blocked_workflow_ids` | `list[str]` | `[]` |
| `event_type` | `Optional[str]` | `None` |
| `debug` | `bool` | `False` |

## `RouteResponse`

| Field | Type | Meaning |
| --- | --- | --- |
| `request_id` | `str` | Caller-provided or generated trace ID |
| `decision` | `Decision` | `ROUTE`, `CLARIFY`, or `LLM_REQUIRED` |
| `workflow_id` | `Optional[str]` | Selected workflow when applicable |
| `confidence` | `float` | Calibrated top confidence, 0–1 |
| `reason_code` | `str` | Stable machine-readable decision reason |
| `missing_inputs` | `list[str]` | Required values to collect |
| `confirmation_required` | `bool` | Whether the contract declares confirmation |
| `model_version` | `str` | Retriever plus verifier version |
| `calibration_version` | `str` | Threshold bundle version |
| `catalog_version` | `str` | Active catalog version |
| `runtime_mode` | `str` | `development`, `shadow`, or `production` |
| `latency_ms` | `float` | Routing latency |
| `candidates` | `Optional[list[CandidateScore]]` | Present only in debug mode |

## `WorkflowContract`

See [Workflow contracts](../guides/workflow-contracts.md) for field semantics and examples.

## Enums

```python
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
```

## Backend protocols

A custom retriever exposes:

```python
class Retriever(Protocol):
    model_version: str
    production_capable: bool

    def prepare(
        self,
        workflows: Sequence[WorkflowContract],
    ) -> None: ...

    def rank(
        self,
        query: str,
        workflows: Sequence[WorkflowContract],
        *,
        top_k: int,
    ) -> list[RetrievalHit]: ...
```

A custom verifier exposes:

```python
class Verifier(Protocol):
    model_version: str
    production_capable: bool

    def verify(
        self,
        query: str,
        context: dict[str, object],
        contract: WorkflowContract,
        retrieval: RetrievalHit,
    ) -> CandidateScore: ...

    def verify_many(
        self,
        query: str,
        context: dict[str, object],
        pairs: Sequence[tuple[WorkflowContract, RetrievalHit]],
    ) -> list[CandidateScore]: ...
```

Use immutable, meaningful `model_version` values because they are returned on every route and
bound into production manifests. A custom backend must explicitly declare
`production_capable = True` before production mode will accept it. That declaration is an
integration contract, not evidence of model quality; your artifact approval remains authoritative.

## Production runtime types

| Type | Responsibility |
| --- | --- |
| `RouterRuntimeConfig` | Development, shadow, or fail-closed production behavior |
| `ArtifactManifest` | Immutable compatibility and approval record |
| `RouterRuntime` | Atomic bundle replacement and rollback |
| `RuntimeSnapshot` | Generation and active artifact lineage |
| `ApiSettings` | HTTP body, host, CORS, documentation, and authorizer requirements |

See [Production mode](../operations/production-mode.md) for an integrated example.
