# Troubleshooting

## Every request returns `NO_WORKFLOW`

Check:

- the catalog contains active workflows;
- descriptions and positive capabilities use language found in real requests;
- the caller's allowlist has not removed every relevant workflow;
- `min_retrieval_score` belongs to the current backend; and
- catalog embeddings were rebuilt after model or serializer changes.

Do not copy a threshold calibrated for one model into another model's score space.

## A valid request returns `CLARIFY`

Inspect `missing_inputs`. Pass authoritative values in `context` under the declared input name
or alias:

```python
RouteRequest(
    text="Cancel my design review",
    context={"event_id": "evt_123"},
)
```

If using text extraction, test the regex independently. A named `value` group returns only the
desired value.

## The API returns HTTP 409

The requested `catalog_version` differs from the active snapshot. Refresh the caller's version
or intentionally omit it when strict catalog lineage is not required.

Do not silently rewrite the requested version inside the service.

## An empty allowlist blocks all workflows

This is intentional:

- omitted or `null` → all otherwise eligible workflows;
- `[]` → no eligible workflows.

This distinction prevents an authorization service that returns zero permissions from
accidentally opening access.

## A reasoning request reaches retrieval

`RoutingPolicy` has `reject_reasoning_requests` and `reject_multi_action_requests` flags.
Confirm they have not been disabled. The v0.2 guards use explicit regex rules and do not cover
every possible phrasing; expand policy tests for your traffic.

## High-risk workflows rarely route

Higher thresholds are expected to reduce coverage. Before lowering them:

1. review the false-route target for that risk tier;
2. inspect false positives and hard negatives;
3. improve training and contract exclusions;
4. refit calibration on representative data; and
5. validate on the untouched hidden test.

Low coverage can be the correct operating point when false execution is costly.

## Candidate scores appear in a client response

`debug=True` includes internal candidate details. Keep it false for normal public requests unless
you have reviewed the data exposure and need it.

## The demo passes but real traffic performs poorly

The included fixture set is a code-path regression suite. It is small and coupled to the demo
catalog. Build representative, workflow-disjoint evaluation data with real near misses and
out-of-scope requests.

## Documentation does not build

```bash
pip install -r requirements-docs.txt
mkdocs build --strict
```

Run from the repository root. If strict mode reports a missing link, preserve the navigation paths
in `mkdocs.yml` or update the relative Markdown link.
