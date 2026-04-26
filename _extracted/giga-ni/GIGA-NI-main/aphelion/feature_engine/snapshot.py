from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

from .utils import ensure_json_serializable


Scalar = float | int | bool | str | None
FeatureValue = Scalar | dict[str, Scalar]


@dataclass(frozen=True, slots=True)
class FeatureSnapshot:
    ts_event_ns: int
    symbol: str
    timeframe: str
    feature_version: str
    warmup_complete: bool
    missing_count: int
    features: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_record(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["event_type"] = "FeatureSnapshot"
        return ensure_json_serializable(payload)


def build_feature_snapshot(
    *,
    ts_event_ns: int,
    symbol: str,
    timeframe: str,
    feature_version: str,
    warmup_complete: bool,
    missing_count: int,
    features: Mapping[str, Any],
    metadata: Mapping[str, Any] | None = None,
) -> FeatureSnapshot:
    snapshot_metadata = dict(metadata or {})
    snapshot_metadata.setdefault("ms_microstructure_ready", False)
    snapshot = FeatureSnapshot(
        ts_event_ns=ts_event_ns,
        symbol=symbol,
        timeframe=timeframe,
        feature_version=feature_version,
        warmup_complete=warmup_complete,
        missing_count=missing_count,
        features=dict(features),
        metadata=snapshot_metadata,
    )
    validate_feature_snapshot(snapshot)
    return snapshot


def flatten_feature_snapshot(snapshot: FeatureSnapshot) -> dict[str, Scalar]:
    flattened: dict[str, Scalar] = {
        "ts_event_ns": snapshot.ts_event_ns,
        "symbol": snapshot.symbol,
        "timeframe": snapshot.timeframe,
        "warmup_complete": snapshot.warmup_complete,
        "missing_count": snapshot.missing_count,
    }

    def visit(prefix: str, value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                nested_prefix = f"{prefix}.{key}" if prefix else key
                visit(nested_prefix, item)
            return
        flattened[prefix] = value

    visit("", snapshot.features)
    return flattened


def validate_feature_snapshot(snapshot: FeatureSnapshot) -> None:
    if not snapshot.symbol:
        raise ValueError("FeatureSnapshot.symbol must be non-empty.")
    if not snapshot.timeframe:
        raise ValueError("FeatureSnapshot.timeframe must be non-empty.")
    ensure_json_serializable(snapshot.to_record())
