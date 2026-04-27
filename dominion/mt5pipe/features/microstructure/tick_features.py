"""
Compute M5-aligned microstructure features from canonical tick data.

The builder intentionally reads the canonical merged tick feed produced by
mt5pipe and returns one feature row per requested M5 bar timestamp.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import polars as pl
import structlog

log = structlog.get_logger(__name__)

BAR_DURATION_MS = 300_000


def _zero_features() -> dict[str, float]:
    return {
        "ofi": 0.0,
        "ofi_abs": 0.0,
        "buy_vol_ratio": 0.5,
        "sell_vol_ratio": 0.5,
        "tick_count": 0.0,
        "tick_rate": 0.0,
        "spread_mean_bps": 0.0,
        "spread_std_bps": 0.0,
        "spread_max_bps": 0.0,
        "realized_vol": 0.0,
        "quote_revision": 0.0,
        "bid_pressure": 0.0,
        "ask_pressure": 0.0,
        "broker_mid_divergence": 0.0,
        "conflict_rate": 0.0,
    }


def _zero_frame(row_count: int) -> pl.DataFrame:
    if row_count <= 0:
        return pl.DataFrame({key: pl.Series([], dtype=pl.Float64) for key in _zero_features()})
    return pl.DataFrame([_zero_features() for _ in range(row_count)])


def _first_existing(columns: list[str], candidates: list[str]) -> str | None:
    for candidate in candidates:
        if candidate in columns:
            return candidate
    return None


def _series_or_default(ticks: pl.DataFrame, candidates: list[str], default: float) -> np.ndarray:
    col = _first_existing(ticks.columns, candidates)
    if col is None:
        return np.full(len(ticks), default, dtype=np.float64)
    return ticks[col].cast(pl.Float64, strict=False).fill_null(default).fill_nan(default).to_numpy()


def compute_bar_tick_features(ticks: pl.DataFrame) -> dict[str, float]:
    """Aggregate one M5 window of canonical ticks into microstructure features."""

    if ticks.is_empty():
        return _zero_features()

    bid_col = _first_existing(ticks.columns, ["bid", "bid_price", "broker_a_bid"])
    ask_col = _first_existing(ticks.columns, ["ask", "ask_price", "broker_a_ask"])
    if bid_col is None or ask_col is None:
        log.warning("tick_quote_columns_missing", columns=ticks.columns)
        return _zero_features()

    flags = _series_or_default(ticks, ["flags", "flag"], 0.0).astype(np.int32)
    volume = _series_or_default(ticks, ["volume", "volume_real", "last_volume", "tick_volume"], 1.0)
    bid = ticks[bid_col].cast(pl.Float64, strict=False).fill_null(0.0).fill_nan(0.0).to_numpy()
    ask = ticks[ask_col].cast(pl.Float64, strict=False).fill_null(0.0).fill_nan(0.0).to_numpy()
    valid_quotes = (bid > 0.0) & (ask > 0.0)
    if not valid_quotes.any():
        return _zero_features()

    bid = bid[valid_quotes]
    ask = ask[valid_quotes]
    flags = flags[valid_quotes]
    volume = volume[valid_quotes]
    mid = (bid + ask) / 2.0
    n = len(mid)

    is_buy = (flags & 32) > 0
    is_sell = (flags & 64) > 0
    buy_vol = float(volume[is_buy].sum())
    sell_vol = float(volume[is_sell].sum())
    total_vol = buy_vol + sell_vol
    ofi = (buy_vol - sell_vol) / (total_vol + 1e-10)

    spread = np.maximum(ask - bid, 0.0)
    avg_mid = float(np.mean(mid)) if n else 1.0
    spread_mean_bps = float(np.mean(spread)) / avg_mid * 10_000 if avg_mid > 0 else 0.0
    spread_std_bps = float(np.std(spread)) / avg_mid * 10_000 if avg_mid > 0 else 0.0
    spread_max_bps = float(np.max(spread)) / avg_mid * 10_000 if avg_mid > 0 else 0.0

    n_bid = int(((flags & 2) > 0).sum())
    n_ask = int(((flags & 4) > 0).sum())
    quote_revision = (n_bid + n_ask) / max(n, 1)

    if n > 1:
        log_ret = np.diff(np.log(np.clip(mid, 1e-10, None)))
        rv = float(np.sum(log_ret**2))
    else:
        rv = 0.0

    broker_divergence = 0.0
    if {"broker_a_bid", "broker_a_ask", "broker_b_bid", "broker_b_ask"}.issubset(set(ticks.columns)):
        ba_mid = (
            ticks["broker_a_bid"].cast(pl.Float64, strict=False).to_numpy()
            + ticks["broker_a_ask"].cast(pl.Float64, strict=False).to_numpy()
        ) / 2.0
        bb_mid = (
            ticks["broker_b_bid"].cast(pl.Float64, strict=False).to_numpy()
            + ticks["broker_b_ask"].cast(pl.Float64, strict=False).to_numpy()
        ) / 2.0
        broker_divergence = float(np.nanmean(np.abs(ba_mid - bb_mid)))
        if not np.isfinite(broker_divergence):
            broker_divergence = 0.0

    conflict_rate = 0.0
    conflict_col = _first_existing(ticks.columns, ["conflict_flag", "conflict", "is_conflict"])
    if conflict_col is not None:
        conflict_rate = float(ticks[conflict_col].cast(pl.Float64, strict=False).fill_null(0.0).mean() or 0.0)

    return {
        "ofi": float(ofi),
        "ofi_abs": float(abs(ofi)),
        "buy_vol_ratio": float(buy_vol / (total_vol + 1e-10)) if total_vol > 0 else 0.5,
        "sell_vol_ratio": float(sell_vol / (total_vol + 1e-10)) if total_vol > 0 else 0.5,
        "tick_count": float(n),
        "tick_rate": float(n / (BAR_DURATION_MS / 1000)),
        "spread_mean_bps": float(spread_mean_bps),
        "spread_std_bps": float(spread_std_bps),
        "spread_max_bps": float(spread_max_bps),
        "realized_vol": float(rv),
        "quote_revision": float(quote_revision),
        "bid_pressure": float(n_bid / max(n, 1)),
        "ask_pressure": float(n_ask / max(n, 1)),
        "broker_mid_divergence": float(broker_divergence),
        "conflict_rate": float(conflict_rate),
    }


def _timestamp_expr(df: pl.DataFrame) -> pl.Expr:
    ts_col = _first_existing(df.columns, ["ts_msc", "time_msc", "time_ms"])
    if ts_col is not None:
        return pl.col(ts_col).cast(pl.Int64, strict=False).alias("_tick_ts_ms")

    dt_col = _first_existing(df.columns, ["ts_utc", "time_utc", "timestamp"])
    if dt_col is None:
        raise ValueError("Canonical ticks must contain ts_msc/time_msc/time_ms or a UTC datetime column.")
    return pl.col(dt_col).dt.epoch("ms").alias("_tick_ts_ms")


def build_tick_feature_dataframe(
    canonical_ticks_root: Path,
    symbol: str,
    m5_timestamps_ms: np.ndarray,
) -> pl.DataFrame:
    """
    Aggregate canonical ticks into one feature row per M5 bar timestamp.

    ``canonical_ticks_root`` must point at the ``canonical_ticks`` directory,
    which contains ``symbol=.../date=.../part-*.parquet`` partitions.
    """

    tick_root = Path(canonical_ticks_root) / f"symbol={symbol}"
    if not tick_root.exists():
        log.warning("canonical_ticks_not_found", path=str(tick_root))
        return _zero_frame(len(m5_timestamps_ms))

    tick_files = sorted(tick_root.rglob("part-*.parquet"))
    if not tick_files:
        log.warning("no_tick_files", path=str(tick_root))
        return _zero_frame(len(m5_timestamps_ms))

    log.info("loading_canonical_ticks", files=len(tick_files), symbol=symbol)
    frames = [pl.read_parquet(path) for path in tick_files]
    all_ticks = pl.concat(frames, how="diagonal_relaxed").with_columns(_timestamp_expr(frames[0])).sort("_tick_ts_ms")
    ts_msc = all_ticks["_tick_ts_ms"].to_numpy()
    log.info("ticks_loaded", count=len(ts_msc), symbol=symbol)

    rows: list[dict[str, float]] = []
    for bar_start_ms in m5_timestamps_ms:
        start_ms = int(bar_start_ms)
        end_ms = start_ms + BAR_DURATION_MS
        lo = int(np.searchsorted(ts_msc, start_ms, side="left"))
        hi = int(np.searchsorted(ts_msc, end_ms, side="left"))
        rows.append(compute_bar_tick_features(all_ticks.slice(lo, hi - lo)) if hi > lo else _zero_features())

    df = pl.DataFrame(rows) if rows else _zero_frame(0)
    df = df.with_columns(
        [
            pl.col("ofi").rolling_mean(5).alias("ofi_5bar"),
            pl.col("ofi").rolling_mean(12).alias("ofi_12bar"),
            pl.col("realized_vol").rolling_mean(12).alias("rv_baseline"),
            pl.col("tick_count").rolling_mean(20).alias("tick_baseline"),
        ]
    ).with_columns(
        [
            (pl.col("realized_vol") / (pl.col("rv_baseline") + 1e-10)).alias("rv_ratio"),
            (pl.col("tick_rate") / (pl.col("tick_baseline") / (BAR_DURATION_MS / 1000) + 1e-10)).alias(
                "tick_intensity"
            ),
        ]
    )

    log.info("tick_features_built", rows=len(df), cols=len(df.columns), symbol=symbol)
    return df.fill_null(0.0).fill_nan(0.0)
