from pathlib import Path

from flowroute import FlowRouter, RouteRequest, WorkflowRegistry

ROOT = Path(__file__).resolve().parents[1]
registry = WorkflowRegistry.from_yaml(ROOT / "examples" / "workflows.yaml")
router = FlowRouter(registry)

requests = [
    RouteRequest(text="Where is order 4812?"),
    RouteRequest(text="Cancel my meeting tomorrow."),
    RouteRequest(text="Explain quantum entanglement."),
]

for request in requests:
    print(router.route(request).model_dump_json(indent=2))

