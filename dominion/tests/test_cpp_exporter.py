"""Tests for the mt5pipe -> C++ bar exporter."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import polars as pl
import pytest

from mt5pipe.export.cpp_exporter import export_bars_for_cpp


def _write_native_bars(root: Path, broker_id: str, symbol: str, tf: str,
                        date: dt.date, bars: list[dict]) -> None:
    """Write a fake native bars parquet partition."""
    out_dir = (
        root / "native_bars"
        / f"broker={broker_id}" / f"symbol={symbol}"
        / f"timeframe={tf}" / f"date={date.isoformat()}"
    )
    out_dir.mkdir(parents=True)
    df = pl.DataFrame(bars)
    df.write_parquet(out_dir / "part-00000.parquet")


def test_export_basic(tmp_path: Path) -> None:
    broker = "test_broker"
    symbol = "XAUUSD"
    tf = "H1"
    d = dt.date(2024, 1, 2)

    bars = [
        {
            "broker_id": broker, "symbol": symbol, "timeframe": tf,
            "time_utc": dt.datetime(2024, 1, 2, 1, 0, tzinfo=dt.timezone.utc),
            "open": 2000.0, "high": 2010.0, "low": 1995.0, "close": 2005.0,
            "tick_volume": 1000, "spread": 5, "real_volume": 0,
            "ingest_ts": dt.datetime(2024, 1, 2, 1, 1, tzinfo=dt.timezone.utc),
        },
        {
            "broker_id": broker, "symbol": symbol, "timeframe": tf,
            "time_utc": dt.datetime(2024, 1, 2, 2, 0, tzinfo=dt.timezone.utc),
            "open": 2005.0, "high": 2015.0, "low": 2000.0, "close": 2010.0,
            "tick_volume": 1200, "spread": 4, "real_volume": 0,
            "ingest_ts": dt.datetime(2024, 1, 2, 2, 1, tzinfo=dt.timezone.utc),
        },
    ]

    mt5pipe_root = tmp_path / "mt5pipe"
    cpp_root = tmp_path / "cpp_data"
    _write_native_bars(mt5pipe_root, broker, symbol, tf, d, bars)

    out = export_bars_for_cpp(mt5pipe_root, cpp_root, symbol, tf, broker)

    assert out.exists()
    df = pl.read_parquet(out)

    # Check schema
    assert set(df.columns) == {"time", "open", "high", "low", "close",
                                "tick_volume", "spread", "real_volume"}
    assert df["time"].dtype == pl.Int64
    assert df["open"].dtype == pl.Float64
    assert df["spread"].dtype == pl.Int32

    # Check values
    assert len(df) == 2
    assert df["open"][0] == pytest.approx(2000.0)
    assert df["open"][1] == pytest.approx(2005.0)

    # time should be ms since epoch
    assert df["time"][0] == int(
        dt.datetime(2024, 1, 2, 1, 0, tzinfo=dt.timezone.utc).timestamp() * 1000
    )


def test_export_sorted_and_deduped(tmp_path: Path) -> None:
    broker = "b"
    symbol = "XAUUSD"
    tf = "H1"

    ts1 = dt.datetime(2024, 1, 2, 1, 0, tzinfo=dt.timezone.utc)
    ts2 = dt.datetime(2024, 1, 2, 2, 0, tzinfo=dt.timezone.utc)

    def make_bar(ts: dt.datetime, open_: float) -> dict:
        return {
            "broker_id": broker, "symbol": symbol, "timeframe": tf,
            "time_utc": ts, "open": open_, "high": open_ + 5,
            "low": open_ - 5, "close": open_ + 2,
            "tick_volume": 100, "spread": 3, "real_volume": 0,
            "ingest_ts": ts,
        }

    # Write two partitions with a duplicate
    d1 = dt.date(2024, 1, 2)
    bars_p1 = [make_bar(ts2, 2005.0), make_bar(ts1, 2000.0)]  # out of order
    bars_p2 = [make_bar(ts1, 2000.0)]  # duplicate of ts1

    mt5pipe_root = tmp_path / "mt5"
    cpp_root = tmp_path / "cpp"
    _write_native_bars(mt5pipe_root, broker, symbol, tf, d1, bars_p1)
    d2 = dt.date(2024, 1, 3)
    _write_native_bars(mt5pipe_root, broker, symbol, tf, d2, bars_p2)

    out = export_bars_for_cpp(mt5pipe_root, cpp_root, symbol, tf, broker)
    df = pl.read_parquet(out)

    # Should have 2 bars (deduped), sorted ascending
    assert len(df) == 2
    assert df["time"][0] < df["time"][1]


def test_export_skip_if_exists(tmp_path: Path) -> None:
    broker = "b"
    symbol = "XAUUSD"
    tf = "H1"
    d = dt.date(2024, 1, 2)
    ts = dt.datetime(2024, 1, 2, 1, 0, tzinfo=dt.timezone.utc)

    bars = [{
        "broker_id": broker, "symbol": symbol, "timeframe": tf,
        "time_utc": ts, "open": 2000.0, "high": 2010.0, "low": 1995.0,
        "close": 2005.0, "tick_volume": 100, "spread": 3, "real_volume": 0,
        "ingest_ts": ts,
    }]

    mt5pipe_root = tmp_path / "mt5"
    cpp_root = tmp_path / "cpp"
    _write_native_bars(mt5pipe_root, broker, symbol, tf, d, bars)

    # First export
    out1 = export_bars_for_cpp(mt5pipe_root, cpp_root, symbol, tf, broker)
    mtime1 = out1.stat().st_mtime

    # Second export without overwrite - should skip
    out2 = export_bars_for_cpp(mt5pipe_root, cpp_root, symbol, tf, broker, overwrite=False)
    assert out2.stat().st_mtime == mtime1  # unchanged

    # With overwrite - should rewrite
    out3 = export_bars_for_cpp(mt5pipe_root, cpp_root, symbol, tf, broker, overwrite=True)
    # File is rewritten (mtime may change)
    assert out3.exists()


def test_export_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="No native bars found"):
        export_bars_for_cpp(tmp_path / "empty", tmp_path / "cpp", "XAUUSD", "H1", "broker")
