"""
Export HYDRA inference results as a signal tape for the C++ engine.

Output format: Parquet with columns:
  time_ms    int64   — bar timestamp in milliseconds since Unix epoch
  direction  int8    — 0=NONE, 1=LONG, 2=SHORT
  confidence float32 — 0.0 to 1.0
  regime     int8    — Regime enum value (matches C++ Regime enum)
"""
from __future__ import annotations

import structlog
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aphelion.intelligence.hydra.inference import HydraInferenceResult

log = structlog.get_logger(__name__)

# Direction mapping
DIRECTION_NONE  = 0
DIRECTION_LONG  = 1
DIRECTION_SHORT = 2

# Regime mapping (must match C++ Regime enum exactly)
REGIME_UNKNOWN            = 0
REGIME_TRENDING_UP        = 1
REGIME_TRENDING_DOWN      = 2
REGIME_RANGE_BOUND        = 3
REGIME_VOLATILE_EXPANSION = 4
REGIME_COMPRESSION        = 5
REGIME_TRANSITION         = 6


def export_signal_tape(
    results: list,
    timestamps_ms: np.ndarray,          # int64 array, one per bar
    output_path: Path,
    symbol: str = "XAUUSD",
    timeframe: str = "H1",
    confidence_threshold: float = 0.0,  # 0 = export everything, filter in C++
) -> Path:
    """
    Convert HYDRA inference results to a signal tape Parquet file.

    Args:
        results: List of HydraInferenceResult (one per bar), in bar order.
        timestamps_ms: int64 array of bar timestamps in milliseconds.
        output_path: Directory to write to.
        symbol: Symbol name (used in filename).
        timeframe: Timeframe string (used in filename).
        confidence_threshold: Optional pre-filter (usually 0, let C++ filter).

    Returns:
        Path to the written Parquet file.
    """
    assert len(results) == len(timestamps_ms), (
        f"Results ({len(results)}) and timestamps ({len(timestamps_ms)}) must match"
    )

    n = len(results)
    direction  = np.zeros(n, dtype=np.int8)
    confidence = np.zeros(n, dtype=np.float32)
    regime     = np.zeros(n, dtype=np.int8)

    for i, r in enumerate(results):
        if r is None:
            continue
        # Direction: use whichever horizon is configured (default: 15m or 60m)
        # Assumes HydraInferenceResult has .direction (1=LONG, -1=SHORT, 0=HOLD)
        # and .confidence (0.0-1.0) and .regime (int)
        raw_dir = getattr(r, "direction", 0)
        conf    = float(getattr(r, "confidence", 0.0))

        if conf < confidence_threshold:
            direction[i] = DIRECTION_NONE
            confidence[i] = 0.0
        elif raw_dir > 0:
            direction[i] = DIRECTION_LONG
            confidence[i] = conf
        elif raw_dir < 0:
            direction[i] = DIRECTION_SHORT
            confidence[i] = conf
        else:
            direction[i] = DIRECTION_NONE
            confidence[i] = conf

        regime[i] = int(getattr(r, "regime", REGIME_UNKNOWN))

    schema = pa.schema([
        pa.field("time_ms",    pa.int64()),
        pa.field("direction",  pa.int8()),
        pa.field("confidence", pa.float32()),
        pa.field("regime",     pa.int8()),
    ])

    table = pa.table({
        "time_ms":    pa.array(timestamps_ms, type=pa.int64()),
        "direction":  pa.array(direction,  type=pa.int8()),
        "confidence": pa.array(confidence, type=pa.float32()),
        "regime":     pa.array(regime,     type=pa.int8()),
    }, schema=schema)

    output_path = Path(output_path)
    output_path.mkdir(parents=True, exist_ok=True)
    out_file = output_path / f"signal_tape_{symbol}_{timeframe}.parquet"

    pq.write_table(table, out_file, compression="snappy")

    long_count  = int((direction == DIRECTION_LONG).sum())
    short_count = int((direction == DIRECTION_SHORT).sum())
    none_count  = int((direction == DIRECTION_NONE).sum())
    avg_conf    = float(confidence[direction != 0].mean()) if (direction != 0).any() else 0.0

    log.info(
        "signal_tape_exported",
        path=str(out_file),
        bars=n,
        long_signals=long_count,
        short_signals=short_count,
        no_signal=none_count,
        signal_rate_pct=round((long_count + short_count) / n * 100, 1),
        avg_confidence=round(avg_conf, 3),
    )

    return out_file


def load_signal_tape_for_verification(path: Path) -> pd.DataFrame:
    """Load and return signal tape for Python-side verification."""
    df = pq.read_table(path).to_pandas()
    log.info(
        "signal_tape_loaded",
        path=str(path),
        rows=len(df),
        long_count=int((df.direction == DIRECTION_LONG).sum()),
        short_count=int((df.direction == DIRECTION_SHORT).sum()),
        avg_confidence=float(df.loc[df.direction != 0, "confidence"].mean())
        if (df.direction != 0).any()
        else 0.0,
    )
    return df
