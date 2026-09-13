"""Command-line interface for demos, evaluation, and local serving."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from .calibration import CalibrationConfig
from .evaluation import evaluate, load_jsonl
from .models import RouteRequest
from .policy import RoutingPolicy
from .registry import WorkflowRegistry
from .router import FlowRouter
from .runtime import sha256_path
from .serialization import SERIALIZER_VERSION


def build_router(catalog: str, calibration: str | None = None) -> FlowRouter:
    registry = WorkflowRegistry.from_yaml(catalog)
    config = CalibrationConfig.from_yaml(calibration) if calibration else CalibrationConfig()
    return FlowRouter(registry, calibration=config)


def _context(raw: str) -> dict[str, object]:
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise argparse.ArgumentTypeError("context must be a JSON object")
    return value


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="flowroute", description="Route requests to deterministic workflows"
    )
    sub = root.add_subparsers(dest="command", required=True)

    route = sub.add_parser("route", help="route one request")
    route.add_argument("--catalog", required=True)
    route.add_argument("--calibration")
    route.add_argument("--text", required=True)
    route.add_argument("--context", type=_context, default={})
    route.add_argument("--event-type")
    route.add_argument("--allowed", nargs="*")
    route.add_argument("--debug", action="store_true")

    evaluate_cmd = sub.add_parser("evaluate", help="evaluate JSONL fixtures")
    evaluate_cmd.add_argument("--catalog", required=True)
    evaluate_cmd.add_argument("--calibration")
    evaluate_cmd.add_argument("--data", required=True)
    evaluate_cmd.add_argument("--fail-on-error", action="store_true")

    serve = sub.add_parser("serve", help="start the optional FastAPI service")
    serve.add_argument("--catalog", required=True)
    serve.add_argument("--calibration")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)

    inspect_bundle = sub.add_parser(
        "inspect-bundle",
        help="print catalog and calibration identities for an artifact manifest",
    )
    inspect_bundle.add_argument("--catalog", required=True)
    inspect_bundle.add_argument("--calibration", required=True)
    inspect_bundle.add_argument("--top-k", type=int, default=8)
    inspect_bundle.add_argument("--require-production-catalog", action="store_true")

    hash_artifact = sub.add_parser(
        "hash-artifact",
        help="calculate the stable SHA-256 digest of a model file or directory",
    )
    hash_artifact.add_argument("--path", required=True)
    return root


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "hash-artifact":
        print(json.dumps({"sha256": sha256_path(args.path)}, indent=2))
        return 0
    if args.command == "inspect-bundle":
        registry = WorkflowRegistry.from_yaml(args.catalog)
        calibration = CalibrationConfig.from_yaml(args.calibration)
        policy = RoutingPolicy()
        issues = registry.production_issues()
        print(
            json.dumps(
                {
                    "catalog_version": registry.catalog_version,
                    "catalog_content_hash": registry.content_hash,
                    "serializer_version": SERIALIZER_VERSION,
                    "calibration_version": calibration.version,
                    "calibration_content_hash": calibration.content_hash,
                    "policy_content_hash": policy.content_hash,
                    "top_k": args.top_k,
                    "retriever_query_prefix": "",
                    "retriever_document_prefix": "",
                    "verifier_label_order": [
                        "mismatch",
                        "needs_input",
                        "executable",
                    ],
                    "allow_exact_event_routes": False,
                    "production_catalog_issues": issues,
                },
                indent=2,
            )
        )
        return int(args.require_production_catalog and bool(issues))

    router = build_router(args.catalog, args.calibration)
    if args.command == "route":
        response = router.route(
            RouteRequest(
                text=args.text,
                context=args.context,
                event_type=args.event_type,
                allowed_workflow_ids=args.allowed,
                debug=args.debug,
            )
        )
        print(response.model_dump_json(indent=2))
        return 0
    if args.command == "evaluate":
        result = evaluate(router, load_jsonl(args.data))
        print(result.model_dump_json(indent=2))
        return int(args.fail_on_error and bool(result.failures))
    if args.command == "serve":
        try:
            import uvicorn
        except ImportError as exc:
            raise SystemExit('Server support requires: pip install -e ".[api]"') from exc
        from .api import create_app

        uvicorn.run(create_app(router), host=args.host, port=args.port)
        return 0
    return 2
