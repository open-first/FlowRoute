# Contributing

FlowRoute combines a production-hardened runtime with research model scaffolding. Before opening
a change:

1. Keep the router separate from workflow execution.
2. Add a regression test for every routing or abstention behavior change.
3. Never weaken a risk threshold to make one demo example pass.
4. Keep contract serialization deterministic and exclude tenant identity metadata.
5. Document dataset licenses and provenance for all training-data changes.
6. Do not add claimed benchmark numbers without a reproducible evaluation artifact.
7. Preserve fail-closed behavior in production mode.
8. Update the artifact schema or serializer version when compatibility changes.

Run:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python -m flowroute evaluate \
  --catalog examples/workflows.yaml \
  --calibration configs/calibration.yaml \
  --data examples/requests.jsonl \
  --fail-on-error
```

If development dependencies are installed, also run `ruff check .` and `python -m build`.

Documentation changes must also pass:

```bash
mkdocs build --strict
```
