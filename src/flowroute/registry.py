"""Catalog loading, validation, hashing, and lookup."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from .models import CatalogSnapshot, WorkflowContract, WorkflowStatus


class CatalogVersionError(ValueError):
    pass


class WorkflowRegistry:
    DEFAULT_MAX_CATALOG_BYTES = 10 * 1024 * 1024

    def __init__(self, snapshot: CatalogSnapshot):
        self.snapshot = snapshot
        self._by_id = {item.id: item for item in snapshot.workflows}
        canonical = json.dumps(
            snapshot.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        self.content_hash = hashlib.sha256(canonical).hexdigest()

    @property
    def catalog_version(self) -> str:
        return self.snapshot.catalog_version

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> WorkflowRegistry:
        return cls(CatalogSnapshot.model_validate(raw))

    @classmethod
    def from_yaml(
        cls,
        path: str | Path,
        *,
        max_bytes: int = DEFAULT_MAX_CATALOG_BYTES,
    ) -> WorkflowRegistry:
        catalog_path = Path(path)
        if max_bytes < 1:
            raise ValueError("max_bytes must be positive")
        if catalog_path.stat().st_size > max_bytes:
            raise ValueError(f"catalog exceeds the {max_bytes}-byte limit")
        with catalog_path.open("r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle)
        if not isinstance(raw, dict):
            raise ValueError("catalog YAML root must be an object")
        return cls.from_mapping(raw)

    def require_version(self, requested: str | None) -> None:
        if requested is not None and requested != self.catalog_version:
            raise CatalogVersionError(
                f"requested catalog {requested!r}, active catalog is {self.catalog_version!r}"
            )

    def get(self, workflow_id: str) -> WorkflowContract | None:
        return self._by_id.get(workflow_id)

    def active_workflows(self) -> list[WorkflowContract]:
        return [item for item in self.snapshot.workflows if item.status == WorkflowStatus.ACTIVE]

    def event_workflow(self, event_type: str) -> WorkflowContract | None:
        matches = [item for item in self.active_workflows() if event_type in item.event_types]
        return matches[0] if len(matches) == 1 else None

    def production_issues(self) -> list[str]:
        issues: list[str] = []
        event_owners: dict[str, list[str]] = {}
        for workflow in self.active_workflows():
            if workflow.owner == "unknown":
                issues.append(f"{workflow.id}: production workflows must declare an owner")
            for event_type in workflow.event_types:
                event_owners.setdefault(event_type, []).append(workflow.id)
        for event_type, workflow_ids in sorted(event_owners.items()):
            if len(workflow_ids) > 1:
                joined = ", ".join(sorted(workflow_ids))
                issues.append(f"event type {event_type!r} is ambiguous across: {joined}")
        return issues
