"""Small reproducible evaluation harness for routing fixtures."""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from pydantic import Field

from .models import Decision, RouteRequest, StrictModel
from .router import FlowRouter


class EvaluationExample(StrictModel):
    id: str
    text: str
    context: dict[str, Any] = Field(default_factory=dict)
    event_type: str | None = None
    allowed_workflow_ids: tuple[str, ...] | None = None
    expected_decision: Decision
    expected_workflow_id: str | None = None


class EvaluationResult(StrictModel):
    examples: int
    decision_accuracy: float
    exact_outcome_accuracy: float
    route_coverage: float
    false_route_rate: float
    false_routes: int
    routed: int
    failures: list[dict[str, Any]]


def load_jsonl(path: str | Path) -> list[EvaluationExample]:
    examples: list[EvaluationExample] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                examples.append(EvaluationExample.model_validate(json.loads(line)))
            except Exception as exc:
                raise ValueError(f"invalid evaluation row {line_number}: {exc}") from exc
    return examples


def evaluate(router: FlowRouter, examples: Iterable[EvaluationExample]) -> EvaluationResult:
    rows = list(examples)
    failures: list[dict[str, Any]] = []
    decision_correct = 0
    exact_correct = 0
    routed = 0
    false_routes = 0
    for example in rows:
        response = router.route(
            RouteRequest(
                request_id=example.id,
                text=example.text,
                context=example.context,
                event_type=example.event_type,
                allowed_workflow_ids=example.allowed_workflow_ids,
            )
        )
        correct_decision = response.decision == example.expected_decision
        correct_workflow = response.workflow_id == example.expected_workflow_id
        decision_correct += int(correct_decision)
        exact_correct += int(correct_decision and correct_workflow)
        if response.decision == Decision.ROUTE:
            routed += 1
            is_false_route = (
                example.expected_decision != Decision.ROUTE or not correct_workflow
            )
            false_routes += int(is_false_route)
        if not (correct_decision and correct_workflow):
            failures.append(
                {
                    "id": example.id,
                    "expected_decision": example.expected_decision.value,
                    "actual_decision": response.decision.value,
                    "expected_workflow_id": example.expected_workflow_id,
                    "actual_workflow_id": response.workflow_id,
                    "reason_code": response.reason_code,
                    "confidence": response.confidence,
                }
            )
    total = len(rows)
    return EvaluationResult(
        examples=total,
        decision_accuracy=decision_correct / total if total else 0.0,
        exact_outcome_accuracy=exact_correct / total if total else 0.0,
        route_coverage=routed / total if total else 0.0,
        false_route_rate=false_routes / routed if routed else 0.0,
        false_routes=false_routes,
        routed=routed,
        failures=failures,
    )
