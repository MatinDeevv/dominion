"""Canonical pipeline data contract.

``StateSnapshot`` is the single immutable structure that flows through every
stage of the APHELION pipeline:

    data → features → model → signal → execution

All downstream components depend on this contract — never on raw scattered
inputs.  The object carries enough context for any consumer to decide without
ad-hoc parameter passing.
"""

from __future__ import annotations

import structlog

log = structlog.get_logger(__name__)

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

from aphelion.feature_engine.snapshot import FeatureSnapshot


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class StateSnapshot:
    """Immutable market-state envelope passed through the canonical pipeline.

    Attributes
    ----------
    timestamp_utc:
        When this snapshot was captured (must be timezone-aware, UTC).
    symbol:
        Instrument identifier (e.g. ``"XAUUSD"``).
    timeframe:
        Bar timeframe string (e.g. ``"1m"``, ``"1h"``).
    current_price:
        Latest mid / close price.
    atr:
        Current ATR value (``None`` when unavailable during warmup).
    feature_snapshot:
        Full ``FeatureSnapshot`` from the feature engine, or ``None``
        during the warmup period.
    features:
        Flat ``dict`` of feature values for strategy consumption.
        When *feature_snapshot* is present this is typically its
        flattened representation; when absent it may be a legacy dict.
    equity:
        Current account equity (required for sizing decisions).
    open_position_count:
        Number of currently open positions.
    warmup_complete:
        ``True`` once the feature engine warmup period has elapsed.
    metadata:
        Free-form dict for session flags, data-quality indicators, etc.
    """

    timestamp_utc: datetime
    symbol: str
    timeframe: str
    current_price: float
    atr: float | None
    feature_snapshot: FeatureSnapshot | None = None
    features: dict[str, Any] = field(default_factory=dict)
    equity: float = 0.0
    open_position_count: int = 0
    warmup_complete: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


def build_state_snapshot(
    *,
    timestamp_utc: datetime | None = None,
    symbol: str,
    timeframe: str,
    current_price: float,
    atr: float | None = None,
    feature_snapshot: FeatureSnapshot | None = None,
    features: Mapping[str, Any] | None = None,
    equity: float = 0.0,
    open_position_count: int = 0,
    warmup_complete: bool = False,
    metadata: Mapping[str, Any] | None = None,
) -> StateSnapshot:
    """Construct a ``StateSnapshot`` with sensible defaults.

    When *feature_snapshot* is supplied and *features* is ``None``, the
    feature dict is automatically populated from the snapshot.
    """
    log.debug("function_entered", function="build_state_snapshot")
    from aphelion.feature_engine.snapshot import flatten_feature_snapshot

    ts = timestamp_utc or _utcnow()
    feat_dict: dict[str, Any] = dict(features) if features is not None else {}

    if feature_snapshot is not None and not feat_dict:
        feat_dict = flatten_feature_snapshot(feature_snapshot)

    warmup = warmup_complete
    if feature_snapshot is not None:
        warmup = feature_snapshot.warmup_complete

    return StateSnapshot(
        timestamp_utc=ts,
        symbol=symbol,
        timeframe=timeframe,
        current_price=current_price,
        atr=atr,
        feature_snapshot=feature_snapshot,
        features=feat_dict,
        equity=equity,
        open_position_count=open_position_count,
        warmup_complete=warmup,
        metadata=dict(metadata or {}),
    )
