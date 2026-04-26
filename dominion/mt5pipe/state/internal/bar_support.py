"""State-local bar validation, timeframe, and gap helpers.

The state sector intentionally keeps these helpers local instead of importing
from ``mt5pipe.bars`` or ``mt5pipe.quality`` so the sector boundary tests can
enforce that state materialization stays self-contained.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

import polars as pl

from mt5pipe.mt5.constants import TIMEFRAME_SECONDS
from mt5pipe.utils.logging import get_logger

log = get_logger(__name__)


@dataclass
class GapReport:
    """Report of detected gaps for a bar sequence."""

    timeframe: str = ""
    total_expected_bars: int = 0
    actual_bars: int = 0
    missing_bars: int = 0
    gaps: list[dict] = field(default_factory=list)

    @property
    def completeness_pct(self) -> float:
        return (self.actual_bars / self.total_expected_bars * 100.0) if self.total_expected_bars else 0.0


FOREX_CLOSE_WEEKDAY = 4
FOREX_CLOSE_HOUR = 22
FOREX_OPEN_WEEKDAY = 6
FOREX_OPEN_HOUR = 22


def timeframe_to_seconds(tf: str) -> int:
    """Map a timeframe label to seconds.

    ``MN1`` keeps the same 30-day approximation used elsewhere in the repo.
    """
    normalized = tf.strip().upper()
    if normalized == "MN1":
        return 30 * 86400
    seconds = TIMEFRAME_SECONDS.get(normalized)
    if seconds is None:
        raise ValueError(f"Unknown timeframe: {tf}")
    return seconds


def is_forex_closed(ts: dt.datetime) -> bool:
    """Return True when the timestamp falls in the weekend FX closure."""
    weekday = ts.weekday()
    hour = ts.hour
    if weekday == FOREX_CLOSE_WEEKDAY and hour >= FOREX_CLOSE_HOUR:
        return True
    if weekday == 5:
        return True
    if weekday == FOREX_OPEN_WEEKDAY and hour < FOREX_OPEN_HOUR:
        return True
    return False


def validate_bars(df: pl.DataFrame) -> pl.DataFrame:
    """Validate and normalize bar integrity in-place."""
    if df.is_empty():
        return df

    cleaned = df
    for column in ("open", "high", "low", "close"):
        if column in cleaned.columns:
            cleaned = cleaned.filter(pl.col(column) > 0)

    if all(column in cleaned.columns for column in ("open", "high", "low", "close")):
        cleaned = cleaned.with_columns(
            [
                pl.max_horizontal("open", "high", "close").alias("high"),
                pl.min_horizontal("open", "low", "close").alias("low"),
            ]
        )

    if "tick_count" in cleaned.columns:
        cleaned = cleaned.filter(pl.col("tick_count") > 0)

    if all(column in cleaned.columns for column in ("spread_min", "spread_mean", "spread_max")):
        cleaned = cleaned.with_columns(
            [
                pl.min_horizontal("spread_min", "spread_mean", "spread_max").alias("spread_min"),
                pl.max_horizontal("spread_min", "spread_mean", "spread_max").alias("spread_max"),
            ]
        )

    numeric_cols = [column for column in cleaned.columns if cleaned[column].dtype in (pl.Float32, pl.Float64)]
    for column in numeric_cols:
        cleaned = cleaned.filter(pl.col(column).is_finite())

    removed = len(df) - len(cleaned)
    if removed > 0:
        log.info("state_bars_validated", removed=removed, remaining=len(cleaned))
    return cleaned


def detect_gaps(
    df: pl.DataFrame,
    timeframe: str,
    tf_seconds: int,
    *,
    time_col: str = "time_utc",
    skip_weekends: bool = True,
) -> GapReport:
    """Detect missing bars in a sorted bar DataFrame."""
    report = GapReport(timeframe=timeframe, actual_bars=len(df))

    if len(df) < 2:
        report.total_expected_bars = len(df)
        return report

    times = df.sort(time_col)[time_col].to_list()
    total_expected = 0

    for index in range(1, len(times)):
        previous = times[index - 1]
        current = times[index]
        delta_seconds = (current - previous).total_seconds()
        expected_slots = int(delta_seconds / tf_seconds)

        if skip_weekends and expected_slots > 1:
            weekend_slots = 0
            for slot_idx in range(1, expected_slots):
                slot_time = previous + dt.timedelta(seconds=slot_idx * tf_seconds)
                if is_forex_closed(slot_time):
                    weekend_slots += 1
            expected_slots -= weekend_slots

        total_expected += 1

        if expected_slots > 1:
            report.gaps.append(
                {
                    "start": previous,
                    "end": current,
                    "missing_count": expected_slots - 1,
                }
            )

    report.total_expected_bars = total_expected + 1
    report.missing_bars = sum(gap["missing_count"] for gap in report.gaps)
    return report


def fill_bar_gaps(
    df: pl.DataFrame,
    timeframe: str,
    tf_seconds: int,
    *,
    time_col: str = "time_utc",
    skip_weekends: bool = True,
) -> pl.DataFrame:
    """Forward-fill small bar gaps with synthetic flat bars."""
    if df.is_empty() or len(df) < 2:
        return df

    max_fill_bars = max(1, int(86400 / tf_seconds))
    ordered = df.sort(time_col)
    times = ordered[time_col].to_list()
    rows_to_insert: list[dict] = []

    for index in range(1, len(times)):
        previous = times[index - 1]
        current = times[index]
        missing = int((current - previous).total_seconds() / tf_seconds) - 1
        if missing <= 0 or missing > max_fill_bars:
            continue

        previous_row = ordered.row(index - 1, named=True)
        close_value = previous_row.get("close", 0.0)

        for slot in range(1, missing + 1):
            fill_time = previous + dt.timedelta(seconds=slot * tf_seconds)
            if skip_weekends and is_forex_closed(fill_time):
                continue

            fill_row = {
                time_col: fill_time,
                "open": close_value,
                "high": close_value,
                "low": close_value,
                "close": close_value,
                "tick_count": 0,
                "volume_sum": 0.0,
                "mid_return": 0.0,
                "realized_vol": 0.0,
                "spread_mean": previous_row.get("spread_mean", 0.0),
                "spread_max": previous_row.get("spread_max", 0.0),
                "spread_min": previous_row.get("spread_min", 0.0),
                "source_count": 0,
                "conflict_count": 0,
                "_filled": True,
            }
            for meta_column in ("symbol", "timeframe"):
                if meta_column in previous_row:
                    fill_row[meta_column] = previous_row[meta_column]
            rows_to_insert.append(fill_row)

    if not rows_to_insert:
        if "_filled" not in ordered.columns:
            ordered = ordered.with_columns(pl.lit(False).alias("_filled"))
        return ordered

    fill_df = pl.DataFrame(rows_to_insert)
    if "_filled" not in ordered.columns:
        ordered = ordered.with_columns(pl.lit(False).alias("_filled"))

    result = pl.concat([ordered, fill_df], how="diagonal_relaxed").sort(time_col)
    log.info("state_bars_gap_filled", filled=len(rows_to_insert), total=len(result))
    return result
