"""Privacy-conscious routing telemetry interfaces."""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from typing import Protocol

from .models import RouteResponse


class TelemetrySink(Protocol):
    def record(self, response: RouteResponse) -> None: ...


class NullTelemetrySink:
    def record(self, response: RouteResponse) -> None:
        return None


class LoggingTelemetrySink:
    """Emit one structured event without request text or context."""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self.logger = logger or logging.getLogger("flowroute.routing")

    def record(self, response: RouteResponse) -> None:
        event = {
            "event": "flowroute.decision",
            "request_id": response.request_id,
            "decision": response.decision.value,
            "workflow_id": response.workflow_id,
            "confidence": response.confidence,
            "reason_code": response.reason_code,
            "confirmation_required": response.confirmation_required,
            "model_version": response.model_version,
            "calibration_version": response.calibration_version,
            "catalog_version": response.catalog_version,
            "runtime_mode": response.runtime_mode,
            "latency_ms": response.latency_ms,
        }
        self.logger.info(json.dumps(event, sort_keys=True, separators=(",", ":")))


class CallbackTelemetrySink:
    def __init__(self, callback: Callable[[RouteResponse], None]) -> None:
        self.callback = callback

    def record(self, response: RouteResponse) -> None:
        self.callback(response)


class InMemoryTelemetrySink:
    """Thread-safe sink intended for tests and local diagnostics."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._responses: list[RouteResponse] = []

    def record(self, response: RouteResponse) -> None:
        with self._lock:
            self._responses.append(response.model_copy(deep=True))

    def snapshot(self) -> list[RouteResponse]:
        with self._lock:
            return [item.model_copy(deep=True) for item in self._responses]
