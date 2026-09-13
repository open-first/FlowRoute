"""Deterministic policy checks that run before and after model scoring."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, field

from .models import RiskTier, RouteRequest, WorkflowContract, WorkflowStatus

_REASONING_RE = re.compile(
    r"\b(explain|why|recommend|advise|brainstorm|analy[sz]e|write a strategy|"
    r"make a plan|which\b.{0,35}\bbest)\b",
    flags=re.IGNORECASE,
)
_ACTION_RE = re.compile(
    r"\b(send|cancel|delete|remove|create|schedule|book|refund|update|change|"
    r"check|find|pause|resume|download|upload)\b",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True)
class GuardResult:
    allow: bool
    reason_code: str = "POLICY_OK"


@dataclass(frozen=True)
class RoutingPolicy:
    allowed_risk_tiers: frozenset[RiskTier] = field(
        default_factory=lambda: frozenset(RiskTier)
    )
    reject_reasoning_requests: bool = True
    reject_multi_action_requests: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "allowed_risk_tiers",
            frozenset(self.allowed_risk_tiers),
        )

    @property
    def content_hash(self) -> str:
        canonical = json.dumps(
            {
                "allowed_risk_tiers": sorted(
                    item.value for item in self.allowed_risk_tiers
                ),
                "reject_reasoning_requests": self.reject_reasoning_requests,
                "reject_multi_action_requests": self.reject_multi_action_requests,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    def precheck(self, text: str) -> GuardResult:
        if self.reject_reasoning_requests and _REASONING_RE.search(text):
            return GuardResult(False, "OPEN_ENDED_REASONING")
        if self.reject_multi_action_requests and re.search(r"\b(and then|then|and)\b", text, re.I):
            if len(_ACTION_RE.findall(text)) >= 2:
                return GuardResult(False, "MULTI_ACTION_UNSUPPORTED")
        return GuardResult(True)

    def filter_candidates(
        self, request: RouteRequest, workflows: Sequence[WorkflowContract]
    ) -> list[WorkflowContract]:
        allowed = (
            None
            if request.allowed_workflow_ids is None
            else set(request.allowed_workflow_ids)
        )
        blocked = set(request.blocked_workflow_ids)
        return [
            item
            for item in workflows
            if item.status == WorkflowStatus.ACTIVE
            and item.risk_tier in self.allowed_risk_tiers
            and (allowed is None or item.id in allowed)
            and item.id not in blocked
        ]


def confirmation_required(contract: WorkflowContract) -> bool:
    return contract.confirmation != "never"
