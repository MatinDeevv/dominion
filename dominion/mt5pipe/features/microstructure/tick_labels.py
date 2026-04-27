"""
Triple-barrier labels at tick resolution.

For each M5 bar, canonical tick mid-prices decide which barrier was hit
first. If ticks are unavailable, the module falls back to bar-close labels.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import polars as pl
import structlog

log = structlog.get_logger(__name__)


def _first_existing(columns: list[str], candidates: list[str]) -> str | None:
    for candidate in candidates:
        if candidate in columns:
            return candidate
    return None


def _time_ms(df: pl.DataFrame) -> np.ndarray:
    if "time_ms" in df.columns:
        return df["time_ms"].cast(pl.Int64, strict=False).to_numpy()
    dt_col = _first_existing(df.columns, ["time_utc", "timestamp", "bar_start"])
    if dt_col is None:
        raise ValueError("DataFrame must include time_ms or a UTC datetime timestamp column.")
    return df.select(pl.col(dt_col).dt.epoch("ms").alias("time_ms"))["time_ms"].to_numpy()


def _tick_time_expr(df: pl.DataFrame) -> pl.Expr:
    ts_col = _first_existing(df.columns, ["ts_msc", "time_msc", "time_ms"])
    if ts_col is not None:
        return pl.col(ts_col).cast(pl.Int64, strict=False).alias("_tick_ts_ms")
    dt_col = _first_existing(df.columns, ["ts_utc", "time_utc", "timestamp"])
    if dt_col is None:
        raise ValueError("Canonical ticks must contain ts_msc/time_msc/time_ms or a UTC datetime column.")
    return pl.col(dt_col).dt.epoch("ms").alias("_tick_ts_ms")


def _atr_values(m5_df: pl.DataFrame, atr_col: str) -> np.ndarray:
    if atr_col in m5_df.columns:
        atr = m5_df[atr_col].cast(pl.Float64, strict=False).fill_null(0.0).fill_nan(0.0).to_numpy()
        return np.maximum(atr, 1e-10)

    if {"high", "low", "close"}.issubset(set(m5_df.columns)):
        high = m5_df["high"].cast(pl.Float64, strict=False).to_numpy()
        low = m5_df["low"].cast(pl.Float64, strict=False).to_numpy()
        close = m5_df["close"].cast(pl.Float64, strict=False).to_numpy()
        prev_close = np.roll(close, 1)
        prev_close[0] = close[0] if len(close) else 0.0
        tr = np.maximum.reduce([high - low, np.abs(high - prev_close), np.abs(low - prev_close)])
        return np.maximum(pl.Series(tr).rolling_mean(14).fill_null(0.0).to_numpy(), 1e-10)

    raise ValueError(f"Missing ATR column '{atr_col}' and high/low/close fallback columns.")


def compute_tick_precise_labels(
    m5_df: pl.DataFrame,
    canonical_ticks_root: Path,
    symbol: str,
    tp_atr_mult: float = 0.8,
    sl_atr_mult: float = 0.8,
    horizons: dict[str, int] | None = None,
    atr_col: str = "atr_14",
) -> pl.DataFrame:
    """
    For each M5 bar, find the first tick to hit TP or SL.

    Labels use 0=SHORT, 1=HOLD, 2=LONG to match the HYDRA training stack.
    """

    horizons = horizons or {"5m": 1, "15m": 3, "30m": 6}
    tick_root = Path(canonical_ticks_root) / f"symbol={symbol}"
    tick_files = sorted(tick_root.rglob("part-*.parquet")) if tick_root.exists() else []
    if not tick_files:
        log.warning("no_tick_data_falling_back_to_bar_labels", symbol=symbol, path=str(tick_root))
        return _compute_bar_labels(m5_df, tp_atr_mult, sl_atr_mult, horizons, atr_col)

    log.info("loading_ticks_for_labels", files=len(tick_files), symbol=symbol)
    frames = [pl.read_parquet(path) for path in tick_files]
    all_ticks = pl.concat(frames, how="diagonal_relaxed").with_columns(_tick_time_expr(frames[0])).sort("_tick_ts_ms")
    bid_col = _first_existing(all_ticks.columns, ["bid", "bid_price", "broker_a_bid"])
    ask_col = _first_existing(all_ticks.columns, ["ask", "ask_price", "broker_a_ask"])
    if bid_col is None or ask_col is None:
        log.warning("tick_quote_columns_missing_falling_back_to_bar_labels", columns=all_ticks.columns)
        return _compute_bar_labels(m5_df, tp_atr_mult, sl_atr_mult, horizons, atr_col)

    ts_msc = all_ticks["_tick_ts_ms"].to_numpy()
    mid = (
        (all_ticks[bid_col].cast(pl.Float64, strict=False) + all_ticks[ask_col].cast(pl.Float64, strict=False))
        / 2.0
    ).fill_null(0.0).fill_nan(0.0).to_numpy()

    close = m5_df["close"].cast(pl.Float64, strict=False).to_numpy()
    atr = _atr_values(m5_df, atr_col)
    times = _time_ms(m5_df)
    n = len(close)

    label_arrays: dict[str, np.ndarray] = {}
    for label_name, horizon_bars in horizons.items():
        labels = np.ones(n, dtype=np.int64)
        for i in range(max(0, n - horizon_bars)):
            bar_atr = max(float(atr[i]), 1e-10)
            entry_idx = int(np.searchsorted(ts_msc, times[i], side="left"))
            if entry_idx >= len(mid) or mid[entry_idx] <= 0:
                continue

            entry_price = float(mid[entry_idx])
            tp = entry_price + tp_atr_mult * bar_atr
            sl = entry_price - sl_atr_mult * bar_atr
            lo = int(np.searchsorted(ts_msc, times[i], side="right"))
            hi = int(np.searchsorted(ts_msc, times[i + horizon_bars], side="left"))
            if hi <= lo:
                continue

            window = mid[lo:hi]
            tp_hits = np.where(window >= tp)[0]
            sl_hits = np.where(window <= sl)[0]
            tp_idx = int(tp_hits[0]) if len(tp_hits) else int(1e9)
            sl_idx = int(sl_hits[0]) if len(sl_hits) else int(1e9)

            if tp_idx < sl_idx:
                labels[i] = 2
            elif sl_idx < tp_idx:
                labels[i] = 0
            else:
                labels[i] = 1

        label_arrays[f"y_{label_name}"] = labels
        log.info(
            "tick_labels_built",
            horizon=label_name,
            long_pct=round(float((labels == 2).mean() * 100), 1),
            short_pct=round(float((labels == 0).mean() * 100), 1),
            hold_pct=round(float((labels == 1).mean() * 100), 1),
        )

    return m5_df.with_columns([pl.Series(name, values) for name, values in label_arrays.items()])


def _compute_bar_labels(
    m5_df: pl.DataFrame,
    tp_mult: float,
    sl_mult: float,
    horizons: dict[str, int],
    atr_col: str,
) -> pl.DataFrame:
    """Fallback bar-close triple-barrier labels."""

    close = m5_df["close"].cast(pl.Float64, strict=False).to_numpy()
    atr = _atr_values(m5_df, atr_col)
    n = len(close)
    label_arrays: dict[str, np.ndarray] = {}

    for name, horizon_bars in horizons.items():
        labels = np.ones(n, dtype=np.int64)
        for i in range(max(0, n - horizon_bars)):
            entry = float(close[i])
            bar_atr = max(float(atr[i]), 1e-10)
            tp = entry + tp_mult * bar_atr
            sl = entry - sl_mult * bar_atr
            for j in range(i + 1, min(i + horizon_bars + 1, n)):
                if close[j] >= tp:
                    labels[i] = 2
                    break
                if close[j] <= sl:
                    labels[i] = 0
                    break
        label_arrays[f"y_{name}"] = labels

    return m5_df.with_columns([pl.Series(name, values) for name, values in label_arrays.items()])
