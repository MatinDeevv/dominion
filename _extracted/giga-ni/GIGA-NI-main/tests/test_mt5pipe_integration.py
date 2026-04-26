from __future__ import annotations

import datetime as dt
import json
import sys
import unittest
import uuid
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from aphelion.feature_engine.events import BarCloseEvent, SessionEvent, TickEvent
from aphelion.feature_engine.integrations.mt5pipe import (
    MT5PipeReplayConfig,
    load_mt5pipe_events,
    normalize_mt5pipe_timeframe,
    replay_mt5pipe_into_engine,
    resolve_mt5pipe_storage_root,
)


def _write_parquet(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows), path)


class MT5PipeIntegrationTests(unittest.TestCase):
    def _build_mt5pipe_fixture(self) -> tuple[Path, Path]:
        sandbox_root = ROOT / ".tmp_testdata"
        sandbox_root.mkdir(parents=True, exist_ok=True)
        temp_root = sandbox_root / f"mt5pipe-{uuid.uuid4().hex[:8]}"
        temp_root.mkdir(parents=True, exist_ok=True)
        mt5pipe_root = temp_root / "DataPipeline"
        storage_root = mt5pipe_root / "data" / "local_data" / "pipeline_data"
        (mt5pipe_root / "config").mkdir(parents=True, exist_ok=True)
        (mt5pipe_root / "config" / "pipeline.yaml").write_text(
            "storage:\n  root: data/local_data/pipeline_data\n",
            encoding="utf-8",
        )

        canonical_rows = [
            {
                "ts_utc": dt.datetime(2026, 1, 1, 0, 0, 5, tzinfo=dt.timezone.utc),
                "ts_msc": 1_767_225_605_000,
                "symbol": "XAUUSD",
                "bid": 1900.0,
                "ask": 1900.2,
                "last": 1900.1,
                "volume": 3.0,
                "source_primary": "broker_a",
            },
            {
                "ts_utc": dt.datetime(2026, 1, 1, 0, 0, 25, tzinfo=dt.timezone.utc),
                "ts_msc": 1_767_225_625_000,
                "symbol": "XAUUSD",
                "bid": 1900.1,
                "ask": 1900.3,
                "last": 1900.2,
                "volume": 4.0,
                "source_primary": "broker_a",
            },
        ]
        _write_parquet(
            storage_root / "canonical_ticks" / "symbol=XAUUSD" / "date=2026-01-01" / "part-00000.parquet",
            canonical_rows,
        )

        m1_bars = [
            {
                "symbol": "XAUUSD",
                "timeframe": "M1",
                "time_utc": dt.datetime(2026, 1, 1, 0, 0, tzinfo=dt.timezone.utc),
                "open": 1900.0,
                "high": 1900.5,
                "low": 1899.9,
                "close": 1900.3,
                "tick_count": 10,
                "volume_sum": 12.0,
            },
            {
                "symbol": "XAUUSD",
                "timeframe": "M1",
                "time_utc": dt.datetime(2026, 1, 1, 0, 1, tzinfo=dt.timezone.utc),
                "open": 1900.3,
                "high": 1900.6,
                "low": 1900.1,
                "close": 1900.4,
                "tick_count": 11,
                "volume_sum": 10.0,
            },
        ]
        _write_parquet(
            storage_root / "bars" / "symbol=XAUUSD" / "timeframe=M1" / "date=2026-01-01" / "part-00000.parquet",
            m1_bars,
        )

        m15_bars = [
            {
                "symbol": "XAUUSD",
                "timeframe": "M15",
                "time_utc": dt.datetime(2026, 1, 1, 0, 0, tzinfo=dt.timezone.utc),
                "open": 1900.0,
                "high": 1902.0,
                "low": 1899.5,
                "close": 1901.0,
                "tick_count": 150,
                "volume_sum": 180.0,
            }
        ]
        _write_parquet(
            storage_root / "bars" / "symbol=XAUUSD" / "timeframe=M15" / "date=2026-01-01" / "part-00000.parquet",
            m15_bars,
        )

        h1_xau_bars = [
            {
                "symbol": "XAUUSD",
                "timeframe": "H1",
                "time_utc": dt.datetime(2026, 1, 1, 0, 0, tzinfo=dt.timezone.utc),
                "open": 1900.0,
                "high": 1903.0,
                "low": 1898.0,
                "close": 1902.0,
                "tick_count": 600,
                "volume_sum": 500.0,
            }
        ]
        _write_parquet(
            storage_root / "bars" / "symbol=XAUUSD" / "timeframe=H1" / "date=2026-01-01" / "part-00000.parquet",
            h1_xau_bars,
        )

        h1_dxy_bars = [
            {
                "symbol": "DXY",
                "timeframe": "H1",
                "time_utc": dt.datetime(2026, 1, 1, 0, 0, tzinfo=dt.timezone.utc),
                "open": 103.0,
                "high": 103.2,
                "low": 102.9,
                "close": 103.1,
                "tick_count": 100,
                "volume_sum": 50.0,
            }
        ]
        _write_parquet(
            storage_root / "bars" / "symbol=DXY" / "timeframe=H1" / "date=2026-01-01" / "part-00000.parquet",
            h1_dxy_bars,
        )
        return mt5pipe_root, storage_root

    def test_load_mt5pipe_events_normalizes_and_orders(self) -> None:
        mt5pipe_root, storage_root = self._build_mt5pipe_fixture()
        config = MT5PipeReplayConfig(
            mt5pipe_root=mt5pipe_root,
            storage_root=storage_root,
            primary_symbol="XAUUSD",
            start_date=dt.date(2026, 1, 1),
            end_date=dt.date(2026, 1, 1),
            tick_symbols=("XAUUSD",),
            bar_symbols=("XAUUSD",),
            bar_timeframes=("M1",),
        )
        events = load_mt5pipe_events(config)
        self.assertEqual(normalize_mt5pipe_timeframe("H1"), "1h")
        self.assertIsInstance(events[0], SessionEvent)
        self.assertEqual(events[0].session_name, "asian")
        self.assertTrue(any(isinstance(event, TickEvent) for event in events))
        m1_bar = next(event for event in events if isinstance(event, BarCloseEvent))
        expected_close_ns = int(dt.datetime(2026, 1, 1, 0, 1, tzinfo=dt.timezone.utc).timestamp() * 1_000_000_000)
        self.assertEqual(m1_bar.timeframe, "1m")
        self.assertEqual(m1_bar.ts_event_ns, expected_close_ns)

    def test_replay_mt5pipe_into_engine_writes_journals(self) -> None:
        mt5pipe_root, storage_root = self._build_mt5pipe_fixture()
        event_journal = mt5pipe_root / "out" / "events.jsonl"
        snapshot_journal = mt5pipe_root / "out" / "snapshots.jsonl"
        config = MT5PipeReplayConfig(
            mt5pipe_root=mt5pipe_root,
            storage_root=storage_root,
            primary_symbol="XAUUSD",
            start_date=dt.date(2026, 1, 1),
            end_date=dt.date(2026, 1, 1),
            tick_symbols=("XAUUSD",),
            bar_symbols=("XAUUSD", "DXY"),
            bar_timeframes=("M1", "M15", "H1"),
            event_journal_path=event_journal,
            snapshot_journal_path=snapshot_journal,
        )
        snapshots = replay_mt5pipe_into_engine(config)

        self.assertGreater(len(snapshots), 0)
        self.assertTrue(event_journal.exists())
        self.assertTrue(snapshot_journal.exists())
        lines = event_journal.read_text(encoding="utf-8").splitlines()
        snapshot_lines = snapshot_journal.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), len(load_mt5pipe_events(config)))
        self.assertEqual(len(snapshot_lines), len(snapshots))

        payloads = [json.loads(line) for line in snapshot_lines]
        self.assertTrue(any(payload["timeframe"] == "1m" for payload in payloads))
        self.assertTrue(any(payload["timeframe"] == "1h" for payload in payloads))
        h1_snapshot = next(payload for payload in payloads if payload["timeframe"] == "1h")
        self.assertIn("regime", h1_snapshot["features"])
        self.assertIn("cross_asset", h1_snapshot["features"])

    def test_storage_root_resolves_from_mt5pipe_config(self) -> None:
        mt5pipe_root, storage_root = self._build_mt5pipe_fixture()
        resolved = resolve_mt5pipe_storage_root(mt5pipe_root=mt5pipe_root)
        self.assertEqual(resolved, storage_root.resolve())


if __name__ == "__main__":
    unittest.main()
