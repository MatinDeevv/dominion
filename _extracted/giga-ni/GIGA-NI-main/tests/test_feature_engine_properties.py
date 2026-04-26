from __future__ import annotations

import random
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from aphelion.feature_engine.events import BarCloseEvent
from aphelion.feature_engine.features import RegimeStateFeature, TechnicalFeature
from aphelion.feature_engine.features.base import FeatureContext
from aphelion.feature_engine.state import FeatureStateStore


class FeaturePropertyTests(unittest.TestCase):
    def test_technical_indicator_properties_hold_on_random_walk(self) -> None:
        rng = random.Random(42)
        feature = TechnicalFeature(default_timeframe="1m")
        state = feature.initialize_state()
        store = FeatureStateStore()
        price = 1900.0

        for seq in range(1, 260):
            step = rng.uniform(-3.0, 3.0)
            price = max(1.0, price + step)
            high = price + abs(rng.uniform(0.1, 1.5))
            low = max(0.1, price - abs(rng.uniform(0.1, 1.5)))
            bar = BarCloseEvent(seq, seq * 1_000_000, "XAUUSD", "1m", price - 0.5, high, low, price, rng.uniform(50, 250), 40, price)
            feature.update(bar, state, FeatureContext(store, "XAUUSD", bar, "1m"))

        values = feature.value(state)
        for value in values["rsi"].values():
            if value is not None:
                self.assertGreaterEqual(value, 0.0)
                self.assertLessEqual(value, 100.0)
        for value in values["atr"].values():
            if value is not None:
                self.assertGreaterEqual(value, 0.0)
        for bands in values["bollinger"].values():
            self.assertLessEqual(bands["lower"], bands["mid"])
            self.assertLessEqual(bands["mid"], bands["upper"])

    def test_regime_probabilities_sum_to_one(self) -> None:
        feature = RegimeStateFeature(window=16, default_timeframe="1h")
        state = feature.initialize_state()
        store = FeatureStateStore()
        prices = [1900, 1903, 1906, 1908, 1907, 1912, 1918, 1925, 1921, 1916, 1910, 1907, 1914, 1920, 1930, 1940, 1935]

        for seq, close in enumerate(prices, start=1):
            bar = BarCloseEvent(seq, seq * 3_600_000_000_000, "XAUUSD", "1h", close - 1, close + 1, close - 2, close, 100, 40, close)
            feature.update(bar, state, FeatureContext(store, "XAUUSD", bar, "1h"))

        probs = feature.value(state)["probabilities"]
        self.assertAlmostEqual(sum(probs.values()), 1.0, places=9)


if __name__ == "__main__":
    unittest.main()

