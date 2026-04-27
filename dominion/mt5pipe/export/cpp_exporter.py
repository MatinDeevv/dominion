"""
Export mt5pipe native bars to the flat Parquet format expected by the C++ engine.

C++ path convention:
  {cpp_data_root}/{SYMBOL}/{TIMEFRAME}/bars/parts/part-00000.parquet

mt5pipe path convention:
  {mt5pipe_root}/native_bars/broker={broker_id}/symbol={symbol}/timeframe={tf}/date={date}/part-*.parquet

This module bridges the two. Run after any mt5pipe backfill.
"""
from __future__ import annotations

import structlog
import polars as pl
from pathlib import Path
from datetime import date

from mt5pipe.storage.paths import StoragePaths

log = structlog.get_logger(__name__)


def export_bars_for_cpp(
    mt5pipe_root: Path,
    cpp_data_root: Path,
    symbol: str,
    timeframe: str,
    broker_id: str,
    date_from: date | None = None,
    date_to: date | None = None,
    overwrite: bool = False,
) -> Path:
    """
    Read native bars from mt5pipe storage and write to C++ flat format.

    Reads all date partitions for symbol/timeframe/broker, concatenates,
    sorts by time, deduplicates, and writes a single Parquet file per
    symbol/timeframe into the C++ path convention.

    Args:
        mt5pipe_root: Root of mt5pipe storage (same as StoragePaths root).
        cpp_data_root: Root directory for C++ bar data.
        symbol: e.g. "XAUUSD"
        timeframe: e.g. "H1", "M1", "H4"
        broker_id: mt5pipe broker ID used during backfill.
        date_from: Optional start date filter (inclusive).
        date_to: Optional end date filter (inclusive).
        overwrite: If False, skip if output already exists.

    Returns:
        Path to the written Parquet file.
    """
    paths = StoragePaths(mt5pipe_root)

    # Find all date partitions for this symbol/timeframe/broker
    native_bars_root = (
        mt5pipe_root
        / "native_bars"
        / f"broker={broker_id}"
        / f"symbol={symbol}"
        / f"timeframe={timeframe}"
    )

    if not native_bars_root.exists():
        raise FileNotFoundError(
            f"No native bars found at {native_bars_root}\n"
            f"Run: mt5pipe backfill --symbol {symbol} --timeframe {timeframe} first."
        )

    # Collect all parquet files across date partitions
    all_files: list[Path] = []
    for date_dir in sorted(native_bars_root.iterdir()):
        if not date_dir.is_dir() or not date_dir.name.startswith("date="):
            continue
        # Parse date for filtering
        if date_from or date_to:
            try:
                d = date.fromisoformat(date_dir.name.removeprefix("date="))
                if date_from and d < date_from:
                    continue
                if date_to and d > date_to:
                    continue
            except ValueError:
                pass
        all_files.extend(sorted(date_dir.glob("part-*.parquet")))

    if not all_files:
        raise FileNotFoundError(
            f"No parquet files found under {native_bars_root} "
            f"(date_from={date_from}, date_to={date_to})"
        )

    log.info(
        "cpp_export_reading",
        symbol=symbol,
        timeframe=timeframe,
        broker_id=broker_id,
        file_count=len(all_files),
    )

    # Determine output path
    out_dir = cpp_data_root / symbol / timeframe / "bars" / "parts"
    out_file = out_dir / "part-00000.parquet"

    if out_file.exists() and not overwrite:
        log.info("cpp_export_skip_exists", path=str(out_file))
        return out_file

    # Read all partitions
    frames = []
    for f in all_files:
        try:
            df = pl.read_parquet(f)
            frames.append(df)
        except Exception as exc:
            log.warning("cpp_export_skip_corrupted", path=str(f), error=str(exc))

    if not frames:
        raise RuntimeError("All parquet files failed to load")

    df = pl.concat(frames)

    # Select and rename columns to match C++ schema:
    #   time_utc → time (as int64 milliseconds since epoch)
    #   tick_volume, spread, real_volume stay the same

    # Convert time_utc (Datetime) to int64 milliseconds
    if "time_utc" in df.columns:
        df = df.with_columns(
            pl.col("time_utc").dt.epoch(time_unit="ms").alias("time")
        )
    elif "time" not in df.columns:
        raise ValueError(f"No time_utc or time column found. Columns: {df.columns}")

    # Select only the columns C++ needs, in order
    keep = ["time", "open", "high", "low", "close"]

    if "tick_volume" in df.columns:
        keep.append("tick_volume")
    else:
        df = df.with_columns(pl.lit(0).cast(pl.Int64).alias("tick_volume"))
        keep.append("tick_volume")

    if "spread" in df.columns:
        keep.append("spread")
    else:
        df = df.with_columns(pl.lit(0).cast(pl.Int32).alias("spread"))
        keep.append("spread")

    if "real_volume" in df.columns:
        keep.append("real_volume")
    else:
        df = df.with_columns(pl.lit(0).cast(pl.Int64).alias("real_volume"))
        keep.append("real_volume")

    df = df.select(keep)

    # Cast to exact types C++ expects
    df = df.with_columns([
        pl.col("time").cast(pl.Int64),
        pl.col("open").cast(pl.Float64),
        pl.col("high").cast(pl.Float64),
        pl.col("low").cast(pl.Float64),
        pl.col("close").cast(pl.Float64),
        pl.col("tick_volume").cast(pl.Int64),
        pl.col("spread").cast(pl.Int32),
        pl.col("real_volume").cast(pl.Int64),
    ])

    # Sort by time ascending, deduplicate
    df = df.sort("time").unique(subset=["time"], keep="first", maintain_order=True)

    if df.is_empty():
        raise RuntimeError("No bars remain after sort and dedup")

    # Write output
    out_dir.mkdir(parents=True, exist_ok=True)
    df.write_parquet(out_file, compression="snappy")

    bar_count = len(df)
    time_min = df["time"][0]
    time_max = df["time"][-1]

    log.info(
        "cpp_export_complete",
        path=str(out_file),
        symbol=symbol,
        timeframe=timeframe,
        bars=bar_count,
        time_min_ms=time_min,
        time_max_ms=time_max,
        size_mb=round(out_file.stat().st_size / 1_048_576, 2),
    )

    return out_file


def export_all_timeframes_for_cpp(
    mt5pipe_root: Path,
    cpp_data_root: Path,
    symbol: str,
    broker_id: str,
    timeframes: list[str] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    overwrite: bool = False,
) -> dict[str, Path]:
    """
    Export all available timeframes for a symbol to C++ format.

    Returns a dict of {timeframe: output_path}.
    """
    if timeframes is None:
        # Auto-discover from mt5pipe storage
        native_bars_root = (
            mt5pipe_root / "native_bars" / f"broker={broker_id}" / f"symbol={symbol}"
        )
        if not native_bars_root.exists():
            raise FileNotFoundError(f"No native bars found at {native_bars_root}")
        timeframes = [
            d.name.removeprefix("timeframe=")
            for d in sorted(native_bars_root.iterdir())
            if d.is_dir() and d.name.startswith("timeframe=")
        ]

    results: dict[str, Path] = {}
    for tf in timeframes:
        try:
            path = export_bars_for_cpp(
                mt5pipe_root=mt5pipe_root,
                cpp_data_root=cpp_data_root,
                symbol=symbol,
                timeframe=tf,
                broker_id=broker_id,
                date_from=date_from,
                date_to=date_to,
                overwrite=overwrite,
            )
            results[tf] = path
        except FileNotFoundError as e:
            log.warning("cpp_export_skip_missing", timeframe=tf, reason=str(e))
        except Exception as e:
            log.error("cpp_export_failed", timeframe=tf, error=str(e))

    return results
