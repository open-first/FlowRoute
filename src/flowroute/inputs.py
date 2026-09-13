"""Deterministic input resolution for routing-time completeness checks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import regex

from .models import InputSpec, WorkflowContract

DEFAULT_REGEX_TIMEOUT_SECONDS = 0.025


@dataclass(frozen=True)
class InputResolution:
    values: dict[str, Any]
    missing: list[str]
    extraction_timeouts: list[str]


def _context_value(context: dict[str, Any], path: str) -> Any | None:
    if path in context:
        return context[path]
    current: Any = context
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _present(value: Any) -> bool:
    return value is not None and value != "" and value != [] and value != {}


def resolve_input(
    spec: InputSpec,
    text: str,
    context: dict[str, Any],
    *,
    regex_timeout_seconds: float = DEFAULT_REGEX_TIMEOUT_SECONDS,
) -> Any | None:
    value, _ = _resolve_input(
        spec,
        text,
        context,
        regex_timeout_seconds=regex_timeout_seconds,
    )
    return value


def _resolve_input(
    spec: InputSpec,
    text: str,
    context: dict[str, Any],
    *,
    regex_timeout_seconds: float,
) -> tuple[Any | None, bool]:
    for key in [spec.name, *spec.aliases]:
        value = _context_value(context, key)
        if _present(value):
            return value, False
    if spec.pattern:
        try:
            match = regex.search(
                spec.pattern,
                text,
                flags=regex.IGNORECASE,
                timeout=regex_timeout_seconds,
            )
        except TimeoutError:
            return None, True
        if match:
            if "value" in match.groupdict():
                return match.group("value"), False
            return match.group(0), False
    return None, False


def resolve_required_inputs(
    contract: WorkflowContract,
    text: str,
    context: dict[str, Any],
    *,
    regex_timeout_seconds: float = DEFAULT_REGEX_TIMEOUT_SECONDS,
) -> InputResolution:
    values: dict[str, Any] = {}
    missing: list[str] = []
    extraction_timeouts: list[str] = []
    for spec in contract.required_inputs:
        value, timed_out = _resolve_input(
            spec,
            text,
            context,
            regex_timeout_seconds=regex_timeout_seconds,
        )
        if timed_out:
            extraction_timeouts.append(spec.name)
        if _present(value):
            values[spec.name] = value
        else:
            missing.append(spec.name)
    return InputResolution(
        values=values,
        missing=missing,
        extraction_timeouts=extraction_timeouts,
    )
