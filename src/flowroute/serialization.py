"""Deterministic workflow serialization used by every model backend."""

from __future__ import annotations

import re
from collections.abc import Sequence

from .models import WorkflowContract

SERIALIZER_VERSION = "flowroute-contract-v1"
_SPACE_RE = re.compile(r"\s+")


def normalize_text(value: str) -> str:
    return _SPACE_RE.sub(" ", value.strip())


def _segment(name: str, values: Sequence[str]) -> str:
    clean = [normalize_text(value) for value in values if normalize_text(value)]
    return f"[{name}] " + " ; ".join(clean) if clean else ""


def serialize_contract(contract: WorkflowContract, *, include_examples: bool = True) -> str:
    """Serialize a contract into stable, labeled model input.

    Operational metadata and owner names are deliberately excluded so the
    model learns capabilities instead of tenant-specific identifiers.
    """

    required = [
        f"{item.name}: {item.description}".rstrip(": ") for item in contract.required_inputs
    ]
    optional = [
        f"{item.name}: {item.description}".rstrip(": ") for item in contract.optional_inputs
    ]
    parts = [
        _segment("NAME", [contract.name]),
        _segment("DESCRIPTION", [contract.description]),
        _segment("CAPABILITY", contract.positive_capabilities),
        _segment("EXCLUDES", contract.exclusions),
        _segment("REQUIRES", required),
        _segment("OPTIONAL", optional),
        _segment("PRECONDITION", contract.preconditions),
        _segment("EFFECT", [contract.side_effect.value]),
    ]
    if include_examples:
        parts.append(_segment("EXAMPLES", contract.examples))
    return normalize_text(" ".join(part for part in parts if part))


def serialize_capability(contract: WorkflowContract) -> str:
    """Positive-only representation for first-stage retrieval."""

    values = [
        contract.name,
        contract.description,
        *contract.positive_capabilities,
        *contract.examples,
    ]
    return normalize_text(" ".join(values))
