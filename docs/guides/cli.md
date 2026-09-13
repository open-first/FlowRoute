# Command-line interface

The `flowroute` command supports routing, fixture evaluation, and local HTTP serving.

## Route one request

```bash
flowroute route \
  --catalog examples/workflows.yaml \
  --calibration configs/calibration.yaml \
  --text "Change my account email to ali@example.com" \
  --context '{}' \
  --allowed account.update_email \
  --debug
```

Options:

| Option | Required | Meaning |
| --- | --- | --- |
| `--catalog PATH` | Yes | Workflow catalog YAML |
| `--text TEXT` | Yes | Natural-language request |
| `--calibration PATH` | No | Threshold YAML |
| `--context JSON` | No | Structured JSON object |
| `--event-type TYPE` | No | Trusted event type |
| `--allowed ID ...` | No | Eligible workflow IDs |
| `--debug` | No | Include candidate diagnostics |

!!! warning "Empty `--allowed`"

    Supplying `--allowed` with no IDs produces an empty allowlist and intentionally blocks
    every workflow.

## Evaluate fixtures

```bash
flowroute evaluate \
  --catalog examples/workflows.yaml \
  --calibration configs/calibration.yaml \
  --data examples/requests.jsonl \
  --fail-on-error
```

`--fail-on-error` makes the process exit non-zero when any fixture has an incorrect decision or
workflow ID, which is useful in CI.

The JSON result contains:

- example count;
- decision accuracy;
- exact decision-plus-workflow accuracy;
- route coverage;
- false-route rate;
- number routed and falsely routed; and
- details for every failed fixture.

## Serve the API

```bash
pip install "flowroute[api]"
flowroute serve \
  --catalog examples/workflows.yaml \
  --calibration configs/calibration.yaml \
  --host 127.0.0.1 \
  --port 8000
```

Do not expose the demo server directly to the public internet. Add your platform's authentication,
authorization, rate limiting, transport security, and monitoring.
