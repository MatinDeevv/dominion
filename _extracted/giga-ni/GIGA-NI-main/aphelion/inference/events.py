from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Mapping

import numpy as np

from aphelion.feature_engine.snapshot import FeatureSnapshot

from .feature_schema import flatten_snapshot, snapshot_to_numpy


LOGGER = logging.getLogger("aphelion.inference")


@dataclass(frozen=True, slots=True)
class FeatureEvent:
    ts_event_ns: int
    symbol: str
    timeframe: str
    feature_version: str
    warmup_complete: bool
    missing_count: int
    features: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_snapshot(cls, snapshot: FeatureSnapshot) -> "FeatureEvent":
        return cls(
            ts_event_ns=snapshot.ts_event_ns,
            symbol=snapshot.symbol,
            timeframe=snapshot.timeframe,
            feature_version=snapshot.feature_version,
            warmup_complete=snapshot.warmup_complete,
            missing_count=snapshot.missing_count,
            features=dict(snapshot.features),
            metadata=dict(snapshot.metadata),
        )

    def flatten(self) -> dict[str, Any]:
        return flatten_snapshot(self.features)

    def tick_sensitive_ready(self) -> bool:
        ready = bool(self.metadata.get("ms_microstructure_ready", False))
        if not ready:
            LOGGER.warning(
                "tick_sensitive_inference_blocked symbol=%s timeframe=%s ts_event_ns=%s",
                self.symbol,
                self.timeframe,
                self.ts_event_ns,
            )
        return ready

    def to_numpy(self, *, tick_sensitive: bool = False) -> np.ndarray | None:
        if tick_sensitive and not self.tick_sensitive_ready():
            return None
        return snapshot_to_numpy(self.flatten())
