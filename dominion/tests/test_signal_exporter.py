"""Tests for signal_exporter — no HYDRA model required."""
import numpy as np
import pytest
import pandas as pd
import pyarrow.parquet as pq
from pathlib import Path

from aphelion.intelligence.hydra.signal_exporter import (
    export_signal_tape,
    load_signal_tape_for_verification,
    DIRECTION_NONE,
    DIRECTION_LONG,
    DIRECTION_SHORT,
)


class FakeResult:
    """Minimal stand-in for HydraInferenceResult."""
    def __init__(self, direction: int, confidence: float, regime: int = 0):
        self.direction  = direction
        self.confidence = confidence
        self.regime     = regime


def _make_timestamps(n: int) -> np.ndarray:
    base_ms = 1_700_000_000_000
    return np.array([base_ms + i * 3_600_000 for i in range(n)], dtype=np.int64)


def test_export_basic_shape(tmp_path: Path):
    results     = [FakeResult(1, 0.75, 1), FakeResult(-1, 0.60, 2), FakeResult(0, 0.0, 0)]
    timestamps  = _make_timestamps(3)
    out_file    = export_signal_tape(results, timestamps, tmp_path, "XAUUSD", "H1")
    df          = pq.read_table(out_file).to_pandas()
    assert len(df) == 3
    assert list(df.columns) == ["time_ms", "direction", "confidence", "regime"]


def test_export_directions_correct(tmp_path: Path):
    results    = [FakeResult(1, 0.80), FakeResult(-1, 0.70), FakeResult(0, 0.0)]
    timestamps = _make_timestamps(3)
    out_file   = export_signal_tape(results, timestamps, tmp_path)
    df         = pq.read_table(out_file).to_pandas()
    assert df.direction.iloc[0] == DIRECTION_LONG
    assert df.direction.iloc[1] == DIRECTION_SHORT
    assert df.direction.iloc[2] == DIRECTION_NONE


def test_export_dtypes(tmp_path: Path):
    results    = [FakeResult(1, 0.55, 3)]
    timestamps = _make_timestamps(1)
    out_file   = export_signal_tape(results, timestamps, tmp_path)
    tbl        = pq.read_table(out_file)
    import pyarrow as pa
    assert tbl.schema.field("time_ms").type    == pa.int64()
    assert tbl.schema.field("direction").type  == pa.int8()
    assert tbl.schema.field("confidence").type == pa.float32()
    assert tbl.schema.field("regime").type     == pa.int8()


def test_export_filename(tmp_path: Path):
    results    = [FakeResult(1, 0.9, 1)]
    timestamps = _make_timestamps(1)
    out_file   = export_signal_tape(results, timestamps, tmp_path, "BTCUSD", "M15")
    assert out_file.name == "signal_tape_BTCUSD_M15.parquet"


def test_confidence_threshold_filters(tmp_path: Path):
    # All below threshold — should be emitted as NONE
    results    = [FakeResult(1, 0.30), FakeResult(-1, 0.25)]
    timestamps = _make_timestamps(2)
    out_file   = export_signal_tape(
        results, timestamps, tmp_path, confidence_threshold=0.50
    )
    df = pq.read_table(out_file).to_pandas()
    assert (df.direction == DIRECTION_NONE).all()


def test_none_result_handled(tmp_path: Path):
    results    = [None, FakeResult(1, 0.70)]
    timestamps = _make_timestamps(2)
    out_file   = export_signal_tape(results, timestamps, tmp_path)
    df         = pq.read_table(out_file).to_pandas()
    assert df.direction.iloc[0] == DIRECTION_NONE
    assert df.direction.iloc[1] == DIRECTION_LONG


def test_load_verification_round_trip(tmp_path: Path):
    results    = [FakeResult(1, 0.80, 1), FakeResult(-1, 0.65, 2)]
    timestamps = _make_timestamps(2)
    out_file   = export_signal_tape(results, timestamps, tmp_path)
    df         = load_signal_tape_for_verification(out_file)
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 2
    assert df.direction.dtype in (np.int8, np.int64, "int8")


def test_mismatched_lengths_raises(tmp_path: Path):
    with pytest.raises(AssertionError):
        export_signal_tape(
            [FakeResult(1, 0.5)],
            _make_timestamps(3),  # length mismatch
            tmp_path,
        )
