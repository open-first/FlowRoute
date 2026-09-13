"""Risk-tier decision thresholds and probability temperature scaling."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import yaml
from pydantic import Field, model_validator

from .models import RiskTier, StrictModel


class TierThreshold(StrictModel):
    route: float = Field(ge=0.0, le=1.0)
    margin: float = Field(ge=0.0, le=1.0)


class CalibrationConfig(StrictModel):
    version: str = "baseline-uncalibrated-0.1.0"
    temperature: float = Field(default=1.0, gt=0.0)
    clarify_threshold: float = Field(default=0.55, ge=0.0, le=1.0)
    min_retrieval_score: float = Field(default=0.08, ge=0.0, le=1.0)
    tiers: dict[RiskTier, TierThreshold] = Field(
        default_factory=lambda: {
            RiskTier.LOW: TierThreshold(route=0.55, margin=0.08),
            RiskTier.MEDIUM: TierThreshold(route=0.65, margin=0.12),
            RiskTier.HIGH: TierThreshold(route=0.76, margin=0.18),
            RiskTier.CRITICAL: TierThreshold(route=0.90, margin=0.25),
        }
    )

    @model_validator(mode="after")
    def complete_and_monotonic_tiers(self) -> CalibrationConfig:
        missing = set(RiskTier) - set(self.tiers)
        if missing:
            values = ", ".join(sorted(item.value for item in missing))
            raise ValueError(f"missing calibration tiers: {values}")
        ordered = [self.tiers[item].route for item in RiskTier]
        if ordered != sorted(ordered):
            raise ValueError("route thresholds must not decrease as risk increases")
        return self

    @classmethod
    def from_yaml(cls, path: str | Path) -> CalibrationConfig:
        with Path(path).open("r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle)
        return cls.model_validate(raw)

    def threshold_for(self, tier: RiskTier) -> TierThreshold:
        if tier not in self.tiers:
            raise ValueError(f"no threshold configured for risk tier {tier.value}")
        return self.tiers[tier]

    @property
    def content_hash(self) -> str:
        canonical = json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    def calibrate(self, probability: float) -> float:
        clipped = min(max(probability, 1e-6), 1.0 - 1e-6)
        logit = math.log(clipped / (1.0 - clipped))
        return 1.0 / (1.0 + math.exp(-(logit / self.temperature)))
