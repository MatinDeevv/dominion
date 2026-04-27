"""
Build the HYDRA scalping dataset with bar, tick, and cross-asset features.

This script is intentionally lightweight: it uses mt5pipe's existing parquet
layout, adds M5 technical features, optionally joins canonical tick
microstructure features and cross-asset context, then writes temporal
train/val/test parquet splits plus metadata.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Iterable

import polars as pl
import structlog

log = structlog.get_logger(__name__)

LABEL_COLUMNS = {"y_5m", "y_15m", "y_30m"}
NON_FEATURE_COLUMNS = {
    "time_ms",
    "time_utc",
    "timestamp",
    "bar_start",
    "broker_id",
    "symbol",
    "timeframe",
    "ingest_ts",
}


def _parse_date(value: str) -> dt.date:
    return dt.date.fromisoformat(value)


def _date_range(start: dt.date, end: dt.date) -> Iterable[dt.date]:
    current = start
    while current <= end:
        yield current
        current += dt.timedelta(days=1)


def _read_partitioned_bars(
    root: Path,
    symbol: str,
    timeframe: str,
    start: dt.date,
    end: dt.date,
    broker_id: str,
) -> pl.DataFrame:
    """Read bars from built canonical storage, then native broker storage."""

    roots = [
        root / "bars" / f"symbol={symbol}" / f"timeframe={timeframe}",
        root / "native_bars" / f"broker={broker_id}" / f"symbol={symbol}" / f"timeframe={timeframe}",
        root / "native_bars" / f"broker={broker_id}" / f"symbol={symbol}" / f"timeframe={timeframe.upper()}",
    ]

    for base in roots:
        frames: list[pl.DataFrame] = []
        for day in _date_range(start, end):
            date_dir = base / f"date={day.isoformat()}"
            if not date_dir.exists():
                continue
            for path in sorted(date_dir.glob("*.parquet")):
                frames.append(pl.read_parquet(path))
        if frames:
            df = pl.concat(frames, how="diagonal_relaxed")
            log.info("bars_loaded", rows=len(df), source=str(base))
            return df

    raise FileNotFoundError(
        "No M5 bars found under mt5pipe root. Expected built bars or native bars "
        f"for symbol={symbol} timeframe={timeframe} broker={broker_id}."
    )


def _time_ms_expression(df: pl.DataFrame) -> pl.Expr:
    if "time_ms" in df.columns:
        return pl.col("time_ms").cast(pl.Int64, strict=False).alias("time_ms")

    for col in ["time_utc", "timestamp", "bar_start", "time"]:
        if col not in df.columns:
            continue
        dtype = df.schema[col]
        if dtype.is_temporal():
            return pl.col(col).dt.epoch("ms").alias("time_ms")
        if dtype.is_numeric():
            return pl.col(col).cast(pl.Int64, strict=False).alias("time_ms")
        return pl.col(col).str.to_datetime(strict=False, time_zone="UTC").dt.epoch("ms").alias("time_ms")

    raise ValueError("Bars must include time_ms, time_utc, timestamp, bar_start, or time.")


def _normalize_m5_bars(df: pl.DataFrame, symbol: str, timeframe: str) -> pl.DataFrame:
    rename_map = {}
    if "tick_volume" in df.columns and "volume" not in df.columns:
        rename_map["tick_volume"] = "volume"
    if "volume_sum" in df.columns and "volume" not in df.columns:
        rename_map["volume_sum"] = "volume"
    if rename_map:
        df = df.rename(rename_map)

    if "volume" not in df.columns:
        df = df.with_columns(pl.lit(0.0).alias("volume"))

    df = df.with_columns(_time_ms_expression(df))
    required = ["open", "high", "low", "close", "volume"]
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(f"Bars are missing required OHLCV columns: {missing}")

    return (
        df.with_columns(
            [
                pl.lit(symbol).alias("symbol"),
                pl.lit(timeframe).alias("timeframe"),
                pl.col("open").cast(pl.Float64, strict=False),
                pl.col("high").cast(pl.Float64, strict=False),
                pl.col("low").cast(pl.Float64, strict=False),
                pl.col("close").cast(pl.Float64, strict=False),
                pl.col("volume").cast(pl.Float64, strict=False).fill_null(0.0),
            ]
        )
        .drop_nulls(["open", "high", "low", "close"])
        .unique(subset=["time_ms"], keep="last")
        .sort("time_ms")
    )


def compute_m5_features(m5: pl.DataFrame) -> pl.DataFrame:
    """Add bar-only M5 features used by the scalping model."""

    close = pl.col("close")
    high = pl.col("high")
    low = pl.col("low")
    volume = pl.col("volume")
    prev_close = close.shift(1)

    true_range = pl.max_horizontal(
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    )
    delta = close.diff()
    gain = pl.when(delta > 0).then(delta).otherwise(0.0)
    loss = pl.when(delta < 0).then(-delta).otherwise(0.0)

    m5 = m5.with_columns(
        [
            ((close - close.shift(1)) / (close.shift(1) + 1e-10)).alias("ret_1"),
            ((close - close.shift(3)) / (close.shift(3) + 1e-10)).alias("ret_3"),
            ((close - close.shift(6)) / (close.shift(6) + 1e-10)).alias("ret_6"),
            true_range.alias("true_range"),
            true_range.rolling_mean(14).alias("atr_14"),
            close.ewm_mean(span=9).alias("ema_9"),
            close.ewm_mean(span=21).alias("ema_21"),
            close.ewm_mean(span=50).alias("ema_50"),
            volume.rolling_mean(20).alias("volume_sma_20"),
            ((close - close.rolling_mean(20)) / (close.rolling_std(20) + 1e-10)).alias("close_zscore_20"),
        ]
    ).with_columns(
        [
            (pl.col("ema_9") - pl.col("ema_21")).alias("ema_9_21_spread"),
            (volume / (pl.col("volume_sma_20") + 1e-10)).alias("volume_ratio_20"),
            (100.0 - 100.0 / (1.0 + gain.ewm_mean(span=14) / (loss.ewm_mean(span=14) + 1e-10))).alias(
                "rsi_14"
            ),
            (pl.from_epoch(pl.col("time_ms"), time_unit="ms").dt.hour()).alias("hour_utc"),
            (pl.from_epoch(pl.col("time_ms"), time_unit="ms").dt.weekday()).alias("day_of_week"),
        ]
    )

    if "spread" in m5.columns:
        m5 = m5.with_columns(pl.col("spread").cast(pl.Float64, strict=False).fill_null(0.0).alias("spread_points"))
    elif "spread_mean" in m5.columns:
        m5 = m5.with_columns(pl.col("spread_mean").cast(pl.Float64, strict=False).fill_null(0.0).alias("spread_points"))
    else:
        m5 = m5.with_columns(pl.lit(0.0).alias("spread_points"))

    return m5.fill_null(0.0).fill_nan(0.0).with_columns(pl.col("time_ms").cast(pl.Int64, strict=False))


def _dedupe_join_columns(addition: pl.DataFrame, existing_columns: set[str], prefix: str) -> pl.DataFrame:
    rename = {col: f"{prefix}_{col}" for col in addition.columns if col in existing_columns}
    return addition.rename(rename) if rename else addition


def _continuous_feature_names(df: pl.DataFrame) -> list[str]:
    names: list[str] = []
    for col, dtype in df.schema.items():
        if col in NON_FEATURE_COLUMNS or col in LABEL_COLUMNS or col.startswith("y_"):
            continue
        if dtype.is_numeric():
            names.append(col)
    return names


def _write_splits(df: pl.DataFrame, output: Path, train_ratio: float, val_ratio: float) -> dict[str, int]:
    n = len(df)
    train_end = int(n * train_ratio)
    val_end = int(n * (train_ratio + val_ratio))
    splits = {
        "train": df.slice(0, train_end),
        "val": df.slice(train_end, max(0, val_end - train_end)),
        "test": df.slice(val_end, max(0, n - val_end)),
    }
    counts: dict[str, int] = {}
    for name, split_df in splits.items():
        counts[name] = len(split_df)
        if not split_df.is_empty():
            split_df.write_parquet(output / f"{name}.parquet")
    return counts


def build_dataset(args: argparse.Namespace) -> pl.DataFrame:
    start = _parse_date(args.from_date)
    end = _parse_date(args.to_date)
    mt5pipe_root = Path(args.mt5pipe_root)
    m5 = _read_partitioned_bars(mt5pipe_root, args.symbol, "M5", start, end, args.broker_id)
    m5 = _normalize_m5_bars(m5, args.symbol, "M5")

    start_ms = int(dt.datetime.combine(start, dt.time.min, tzinfo=dt.UTC).timestamp() * 1000)
    end_ms = int(dt.datetime.combine(end + dt.timedelta(days=1), dt.time.min, tzinfo=dt.UTC).timestamp() * 1000)
    m5 = m5.filter((pl.col("time_ms") >= start_ms) & (pl.col("time_ms") < end_ms))
    if m5.is_empty():
        raise ValueError("No M5 bars remain after date filtering.")

    m5 = compute_m5_features(m5)

    tick_root = Path(args.tick_root)
    if not args.no_ticks and tick_root.exists():
        log.info("computing_tick_features", tick_root=str(tick_root), symbol=args.symbol)
        from mt5pipe.features.microstructure.tick_features import build_tick_feature_dataframe

        tick_feats = build_tick_feature_dataframe(
            canonical_ticks_root=tick_root,
            symbol=args.symbol,
            m5_timestamps_ms=m5["time_ms"].to_numpy(),
        )
        tick_feats = _dedupe_join_columns(tick_feats, set(m5.columns), "micro")
        m5 = pl.concat([m5, tick_feats], how="horizontal")
        log.info("tick_features_joined", new_cols=len(tick_feats.columns))
    else:
        log.info(
            "skipping_tick_features",
            reason="no_ticks flag" if args.no_ticks else "tick root not found",
            path=str(tick_root),
        )

    ca_dir = Path(args.cross_asset_dir)
    if not args.no_cross_asset and ca_dir.exists():
        log.info("joining_cross_asset", cross_asset_dir=str(ca_dir))
        from scripts.fetch_cross_asset import build_cross_asset_feature_block

        ca_feats = build_cross_asset_feature_block(
            m5_timestamps_ms=m5["time_ms"].to_numpy(),
            cross_asset_dir=ca_dir,
        )
        m5 = pl.concat([m5, _dedupe_join_columns(ca_feats.drop("time_ms"), set(m5.columns), "cross")], how="horizontal")
        log.info("cross_asset_joined", new_cols=len(ca_feats.columns) - 1)
    else:
        log.info(
            "skipping_cross_asset",
            reason="no_cross_asset flag" if args.no_cross_asset else "dir not found",
            path=str(ca_dir),
        )

    log.info("computing_labels", tick_root=str(tick_root))
    from mt5pipe.features.microstructure.tick_labels import compute_tick_precise_labels

    m5 = compute_tick_precise_labels(
        m5_df=m5,
        canonical_ticks_root=tick_root,
        symbol=args.symbol,
        tp_atr_mult=0.8,
        sl_atr_mult=0.8,
        horizons={"5m": 1, "15m": 3, "30m": 6},
    )
    return m5.fill_null(0.0).fill_nan(0.0).with_columns(pl.col("time_ms").cast(pl.Int64, strict=False))


def write_dataset(df: pl.DataFrame, args: argparse.Namespace) -> None:
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    df.write_parquet(output / "dataset.parquet")
    split_counts = _write_splits(df, output, args.train_ratio, args.val_ratio)

    feature_names = _continuous_feature_names(df)
    metadata = {
        "symbol": args.symbol,
        "timeframe": "M5",
        "from_date": args.from_date,
        "to_date": args.to_date,
        "total_bars": len(df),
        "n_continuous_features": len(feature_names),
        "continuous_feature_names": feature_names,
        "label_columns": [col for col in sorted(LABEL_COLUMNS) if col in df.columns],
        "split_row_counts": split_counts,
        "tick_root": str(args.tick_root),
        "cross_asset_dir": str(args.cross_asset_dir),
    }
    (output / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    log.info(
        "scalping_dataset_written",
        output=str(output),
        bars=len(df),
        continuous_features=len(feature_names),
        splits=split_counts,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build an upgraded HYDRA scalping dataset.")
    parser.add_argument("--mt5pipe-root", default="data/local_data/pipeline_data")
    parser.add_argument("--broker-id", default="broker_a")
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--from-date", default="2022-01-01")
    parser.add_argument("--to-date", default="2026-04-01")
    parser.add_argument("--output", default="data/processed/scalping_v2")
    parser.add_argument(
        "--tick-root",
        default="data/local_data/pipeline_data/canonical_ticks",
        help="Path to canonical_ticks/ dir - enables tick features and precise labels",
    )
    parser.add_argument(
        "--cross-asset-dir",
        default="data/processed/cross_asset",
        help="Path to cross-asset Parquet dir - enables DXY, Silver, VIX features",
    )
    parser.add_argument("--no-ticks", action="store_true", help="Skip tick features.")
    parser.add_argument("--no-cross-asset", action="store_true", help="Skip cross-asset features.")
    parser.add_argument("--train-ratio", type=float, default=0.70)
    parser.add_argument("--val-ratio", type=float, default=0.15)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    df = build_dataset(args)
    write_dataset(df, args)


if __name__ == "__main__":
    main()
