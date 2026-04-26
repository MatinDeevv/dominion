from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from aphelion.feature_engine.engine import FeatureEngine, FeatureEngineConfig
from aphelion.feature_engine.events import BarCloseEvent, SessionEvent, TickEvent
from aphelion.feature_engine.features import MarketStructureFeature, MicrostructureFeature, TechnicalFeature, VWAPFeature
from aphelion.feature_engine.features.base import FeatureContext
from aphelion.feature_engine.registry import FeatureRegistry
from aphelion.feature_engine.state import FeatureStateStore


class FeatureUnitTests(unittest.TestCase):
    def test_microstructure_feature_updates_incrementally(self) -> None:
        feature = MicrostructureFeature(window=4, bucket_volume=10.0, default_timeframe="1m")
        state = feature.initialize_state()
        store = FeatureStateStore()

        ticks = [
            TickEvent(1, 1_000, 1_100, "XAUUSD", 2000.0, 2000.2, 2000.1, 5.0, "mt5", 2.0, 1.0),
            TickEvent(2, 2_000, 2_100, "XAUUSD", 2000.1, 2000.3, 2000.2, 5.0, "mt5", 3.0, 1.0),
            TickEvent(3, 3_000, 3_100, "XAUUSD", 2000.2, 2000.4, 2000.3, 5.0, "mt5", 4.0, 1.0),
            TickEvent(4, 4_000, 4_100, "XAUUSD", 2000.3, 2000.5, 2000.4, 5.0, "mt5", 5.0, 1.0),
        ]

        for event in ticks:
            context = FeatureContext(store, "XAUUSD", event, "1m")
            feature.update(event, state, context)

        values = feature.value(state)
        self.assertGreaterEqual(values["spread"], 0.0)
        self.assertIn("toxicity_index", values)
        self.assertTrue(feature.ready(state))

    def test_market_structure_confirms_swing_and_bos(self) -> None:
        feature = MarketStructureFeature(lookback=2, default_timeframe="15m")
        state = feature.initialize_state()
        store = FeatureStateStore()

        bars = [
            BarCloseEvent(1, 1_000, "XAUUSD", "15m", 99, 100, 95, 98, 10, 100),
            BarCloseEvent(2, 2_000, "XAUUSD", "15m", 98, 102, 97, 101, 10, 100),
            BarCloseEvent(3, 3_000, "XAUUSD", "15m", 101, 105, 100, 104, 10, 100),
            BarCloseEvent(4, 4_000, "XAUUSD", "15m", 104, 103, 99, 100, 12, 100),
            BarCloseEvent(5, 5_000, "XAUUSD", "15m", 101, 101, 97, 98, 14, 100),
            BarCloseEvent(6, 6_000, "XAUUSD", "15m", 98, 106, 98, 106, 18, 100),
        ]

        for event in bars:
            context = FeatureContext(store, "XAUUSD", event, "15m")
            feature.update(event, state, context)

        values = feature.value(state)
        self.assertEqual(values["last_swing_high"], 105)
        self.assertTrue(values["bullish_bos"])
        self.assertEqual(values["trend"], "up")

    def test_vwap_resets_on_session_open(self) -> None:
        feature = VWAPFeature(rolling_window=3, default_timeframe="1m")
        state = feature.initialize_state()
        store = FeatureStateStore()

        session_open = SessionEvent(1, 1_000, "XAUUSD", "london", "open")
        feature.update(session_open, state, FeatureContext(store, "XAUUSD", session_open, "1m"))
        first_bar = BarCloseEvent(2, 2_000, "XAUUSD", "1m", 100, 101, 99, 100, 10, 20, 100)
        second_bar = BarCloseEvent(3, 3_000, "XAUUSD", "1m", 110, 111, 109, 110, 10, 20, 110)
        feature.update(first_bar, state, FeatureContext(store, "XAUUSD", first_bar, "1m"))
        feature.update(second_bar, state, FeatureContext(store, "XAUUSD", second_bar, "1m"))
        first_session_vwap = feature.value(state)["session_vwap"]

        reset = SessionEvent(4, 4_000, "XAUUSD", "new_york", "open")
        feature.update(reset, state, FeatureContext(store, "XAUUSD", reset, "1m"))
        third_bar = BarCloseEvent(5, 5_000, "XAUUSD", "1m", 120, 121, 119, 120, 5, 20, 120)
        feature.update(third_bar, state, FeatureContext(store, "XAUUSD", third_bar, "1m"))
        second_session_vwap = feature.value(state)["session_vwap"]

        self.assertNotEqual(first_session_vwap, second_session_vwap)
        self.assertEqual(second_session_vwap, 120.0)

    def test_engine_emits_bar_snapshot_for_matching_timeframe(self) -> None:
        registry = FeatureRegistry()
        registry.register(TechnicalFeature(default_timeframe="1m"))
        engine = FeatureEngine(registry=registry, config=FeatureEngineConfig(primary_symbol="XAUUSD", default_timeframe="1m"))

        snapshots = []
        for seq in range(1, 220):
            close = 1900.0 + seq
            bar = BarCloseEvent(seq, seq * 1_000_000_000, "XAUUSD", "1m", close - 1, close + 1, close - 2, close, 100.0, 50, close)
            snapshots = engine.on_event(bar)

        self.assertTrue(snapshots)
        snapshot = snapshots[-1]
        self.assertEqual(snapshot.symbol, "XAUUSD")
        self.assertEqual(snapshot.timeframe, "1m")
        self.assertIn("technical", snapshot.features)
        self.assertTrue(snapshot.warmup_complete)


if __name__ == "__main__":
    unittest.main()

