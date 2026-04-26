"""Central integration events for the unified APHELION runtime."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from aphelion.feature_engine.snapshot import FeatureSnapshot


def _coerce_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class MarketContext:
    timestamp_utc: datetime
    symbol: str
    timeframe: str
    current_price: float | None
    atr: float | None
    dual_source_ratio: float = 0.0
    disagreement_pressure_bps: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "timestamp_utc", _coerce_utc(self.timestamp_utc))


@dataclass(frozen=True, slots=True)
class FeatureComputedEvent:
    timestamp_utc: datetime
    source: str
    snapshot: FeatureSnapshot
    market_context: MarketContext

    def __post_init__(self) -> None:
        object.__setattr__(self, "timestamp_utc", _coerce_utc(self.timestamp_utc))


@dataclass(frozen=True, slots=True)
class SignalGeneratedEvent:
    timestamp_utc: datetime
    source: str
    signal: Any
    market_context: MarketContext

    def __post_init__(self) -> None:
        object.__setattr__(self, "timestamp_utc", _coerce_utc(self.timestamp_utc))


@dataclass(frozen=True, slots=True)
class TradeDecisionEvent:
    timestamp_utc: datetime
    source: str
    signal: Any
    approved: bool
    order: Any | None
    reason: str
    market_context: MarketContext

    def __post_init__(self) -> None:
        object.__setattr__(self, "timestamp_utc", _coerce_utc(self.timestamp_utc))


@dataclass(frozen=True, slots=True)
class OrderFilledEvent:
    timestamp_utc: datetime
    source: str
    signal: Any
    order: Any
    fill: Any
    market_context: MarketContext

    def __post_init__(self) -> None:
        object.__setattr__(self, "timestamp_utc", _coerce_utc(self.timestamp_utc))


__all__ = [
    "FeatureComputedEvent",
    "MarketContext",
    "OrderFilledEvent",
    "SignalGeneratedEvent",
    "TradeDecisionEvent",
]
