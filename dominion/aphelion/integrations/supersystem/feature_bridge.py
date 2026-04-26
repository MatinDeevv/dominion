"""Adapters that turn Future-engine snapshots into neural-model-ready history frames."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

import polars as pl

from aphelion.feature_engine.snapshot import FeatureSnapshot, flatten_feature_snapshot


ENGINE_TO_ML_TIMEFRAME = {
    "1m": "M1",
    "2m": "M2",
    "3m": "M3",
    "4m": "M4",
    "5m": "M5",
    "10m": "M10",
    "15m": "M15",
    "20m": "M20",
    "30m": "M30",
    "1h": "H1",
    "2h": "H2",
    "4h": "H4",
    "1d": "D1",
    "1w": "W1",
    "1mo": "MN1",
}

DEFAULT_COLUMN_ALIASES = {
    "spread": "spread_mean",
    "price": "close",
    "close_price": "close",
    "open_price": "open",
    "high_price": "high",
    "low_price": "low",
}


def ns_to_datetime(ts_event_ns: int) -> datetime:
    return datetime.fromtimestamp(ts_event_ns / 1_000_000_000, tz=timezone.utc)


def normalize_timeframe(timeframe: str) -> str:
    normalized = ENGINE_TO_ML_TIMEFRAME.get(timeframe.lower())
    if normalized is not None:
        return normalized
    return timeframe.upper()


def _coerce_scalar(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str, datetime)):
        return value
    return _SKIP


def extract_market_context(snapshot: FeatureSnapshot) -> dict[str, Any]:
    flattened = flatten_feature_snapshot(snapshot)
    close_price = flattened.get(
        "close",
        snapshot.metadata.get(
            "close",
            flattened.get(
                "mid",
                snapshot.metadata.get(
                    "mid",
                    flattened.get("price", snapshot.metadata.get("price")),
                ),
            ),
        ),
    )
    atr = flattened.get("atr", snapshot.metadata.get("atr"))
    return {
        "timestamp_utc": ns_to_datetime(snapshot.ts_event_ns),
        "symbol": snapshot.symbol,
        "timeframe": normalize_timeframe(snapshot.timeframe),
        "current_price": float(close_price) if close_price is not None else None,
        "atr": float(atr) if atr is not None else None,
        "dual_source_ratio": float(
            snapshot.metadata.get("dual_source_ratio", flattened.get("dual_source_ratio", 0.0))
        ),
        "disagreement_pressure_bps": float(
            snapshot.metadata.get(
                "disagreement_pressure_bps",
                flattened.get("disagreement_pressure_bps", flattened.get("disagreement_bps", 0.0)),
            )
        ),
    }


_SKIP = object()


@dataclass
class FeatureSnapshotHistoryBridge:
    """Maintain a rolling inference history from Future-engine feature snapshots."""

    context_len: int = 240
    max_rows: int = 4096
    symbol_index: Mapping[str, int] = field(default_factory=dict)
    column_aliases: Mapping[str, str] = field(default_factory=lambda: DEFAULT_COLUMN_ALIASES)
    _records: list[dict[str, Any]] = field(default_factory=list, init=False, repr=False)

    def append(self, snapshot: FeatureSnapshot) -> dict[str, Any]:
        record = self._snapshot_to_record(snapshot)
        self._records.append(record)
        if len(self._records) > self.max_rows:
            self._records = self._records[-self.max_rows :]
        return record

    def is_ready(self) -> bool:
        return len(self._records) >= self.context_len

    def to_dataframe(self, tail: int | None = None) -> pl.DataFrame:
        if not self._records:
            return pl.DataFrame()
        rows = self._records[-tail:] if tail is not None else self._records
        return pl.DataFrame(rows).sort("time_utc")

    def latest_record(self) -> dict[str, Any]:
        if not self._records:
            raise RuntimeError("No snapshots have been recorded yet.")
        return dict(self._records[-1])

    def latest_bar_metadata(self) -> dict[str, Any]:
        latest = self.latest_record()
        return {
            "timestamp_utc": latest["time_utc"],
            "symbol": latest["symbol"],
            "timeframe": latest["timeframe"],
            "dual_source_ratio": float(latest.get("dual_source_ratio", 0.0) or 0.0),
            "disagreement_pressure_bps": float(latest.get("disagreement_pressure_bps", 0.0) or 0.0),
        }

    def _snapshot_to_record(self, snapshot: FeatureSnapshot) -> dict[str, Any]:
        flattened = flatten_feature_snapshot(snapshot)
        record: dict[str, Any] = {
            "symbol": snapshot.symbol,
            "timeframe": normalize_timeframe(snapshot.timeframe),
            "time_utc": ns_to_datetime(snapshot.ts_event_ns),
            "symbol_idx": int(self.symbol_index.get(snapshot.symbol, 0)),
            "_filled": False,
            "feature_version": snapshot.feature_version,
            "warmup_complete": snapshot.warmup_complete,
            "missing_count": snapshot.missing_count,
        }

        for key, value in flattened.items():
            if key in {"ts_event_ns", "symbol", "timeframe", "warmup_complete", "missing_count"}:
                continue
            alias = self.column_aliases.get(key, key)
            coerced = _coerce_scalar(value)
            if coerced is not _SKIP:
                record[alias] = coerced

        for key, value in snapshot.metadata.items():
            alias = self.column_aliases.get(key, key)
            if alias in record:
                continue
            coerced = _coerce_scalar(value)
            if coerced is not _SKIP:
                record[alias] = coerced

        return record


__all__ = [
    "FeatureSnapshotHistoryBridge",
    "extract_market_context",
    "normalize_timeframe",
    "ns_to_datetime",
]
