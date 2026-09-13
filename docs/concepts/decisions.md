# Decisions and reason codes

FlowRoute has three public decisions. The `reason_code` explains which rule produced that
decision and is more suitable for logs and metrics than parsing free-form text.

## ROUTE

One eligible workflow passed semantic, completeness, ambiguity, and risk checks.

| Reason code | Meaning |
| --- | --- |
| `EXACT_EVENT_RULE` | One trusted event mapped to one workflow and all inputs were present |
| `ACCEPTED_LOW_RISK` | A low-risk semantic route cleared its thresholds |
| `ACCEPTED_MEDIUM_RISK` | A medium-risk semantic route cleared its thresholds |
| `ACCEPTED_HIGH_RISK` | A high-risk semantic route cleared its thresholds |
| `ACCEPTED_CRITICAL_RISK` | A critical-risk semantic route cleared its thresholds |

`ROUTE` does not mean “authorized” or “executed.”

## CLARIFY

The workflow matches, but required input is absent.

| Reason code | Meaning |
| --- | --- |
| `EXACT_EVENT_MISSING_INPUT` | An exact event matched, but a required value was missing |
| `MISSING_REQUIRED_INPUT` | A semantic candidate matched strongly enough to ask for inputs |

Use `missing_inputs` to construct a narrow follow-up question. Validate the answer as a typed
workflow argument before execution.

## LLM_REQUIRED

The deterministic path should not route the request.

| Reason code | Meaning | Suggested handling |
| --- | --- | --- |
| `CATALOG_VERSION_REQUIRED` | Production request omitted catalog lineage | Refresh client configuration and retry |
| `WORKFLOW_ALLOWLIST_REQUIRED` | Production request omitted the authorized candidate set | Fix the authorization integration |
| `DEBUG_DISABLED` | A production request asked for candidate details | Retry without debug output |
| `INVALID_CONTEXT` | Context became non-JSON or non-finite after request construction | Reject or rebuild the request |
| `CONTEXT_TOO_LARGE` | Serialized context exceeded the configured limit | Send only routing-time fields |
| `NO_ELIGIBLE_WORKFLOW` | Policy filtering removed every candidate | Check authorization or return “not available” |
| `AMBIGUOUS_EVENT_RULE` | Multiple workflows declared the event | Fix the catalog; do not guess |
| `OPEN_ENDED_REASONING` | The user requested explanation, analysis, advice, or planning | Send to an LLM or human |
| `MULTI_ACTION_UNSUPPORTED` | The request contains multiple actions | Send to a planner or decompose explicitly |
| `INPUT_EXTRACTION_TIMEOUT` | A contract regex exceeded its execution budget | Fix or remove the pattern |
| `BACKEND_UNAVAILABLE` | Retrieval or verification raised or returned invalid output | Retry, alert, or use the safe fallback |
| `RUNTIME_INTEGRITY_FAILURE` | The active production settings no longer match the approved manifest | Remove from traffic and reload a complete bundle |
| `NO_WORKFLOW` | Retrieval found no plausible candidate | General fallback |
| `AMBIGUOUS_CANDIDATES` | The top candidates were too close | Clarify intent outside FlowRoute or use fallback |
| `LOW_CONFIDENCE_MISSING_INPUT` | The needs-input hypothesis was too weak | General fallback rather than asking a misleading question |
| `BELOW_RISK_THRESHOLD` | The best candidate did not meet its risk threshold | General fallback |

## Recommended application policy

```python
if result.decision == "ROUTE":
    validate_workflow_entry(result)
elif result.decision == "CLARIFY":
    collect_only(result.missing_inputs)
else:
    fallback_by_reason(result.reason_code)
```

Monitor reason-code rates by catalog version, model version, customer or domain slice, language,
and risk tier. A sudden increase in `NO_WORKFLOW` or `AMBIGUOUS_CANDIDATES` can indicate catalog
or traffic drift.
