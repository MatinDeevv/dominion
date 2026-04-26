from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np

from aphelion.feature_engine.snapshot import FeatureSnapshot
from aphelion.inference.events import FeatureEvent
from aphelion.inference.feature_schema import (
    BOOLEAN_FEATURES,
    FEATURE_DIM,
    NUMERIC_FEATURES,
    flatten_snapshot,
    missing_contract_fields,
    snapshot_to_numpy,
    vector_index,
)


def _sample_features() -> dict:
    return {
        "volume_profile": {
            "volume_delta": 1.25,
            "cvd": 5.5,
            "poc": 2650.5,
            "vah": 2660.0,
            "val": 2642.0,
            "delta_divergence": True,
            "absorption": False,
        },
        "vwap": {
            "session_vwap": 2655.0,
            "rolling_vwap": 2658.0,
            "band_up_1": 2665.0,
            "band_down_1": 2645.0,
            "band_up_2": 2670.0,
            "band_down_2": 2640.0,
            "anchors": {
                "session_asian": {
                    "vwap": 2654.0,
                    "band_up_1": 2662.0,
                    "band_down_1": 2646.0,
                }
            },
        },
        "technical": {
            "atr": {"5": 3.0, "10": 4.0, "14": 5.0, "20": 6.0, "50": 7.0},
            "bollinger": {
                "10": {"upper": 10.0, "mid": 9.0, "lower": 8.0},
                "20": {"upper": 20.0, "mid": 19.0, "lower": 18.0},
                "50": {"upper": 50.0, "mid": 49.0, "lower": 48.0},
            },
            "rsi": {"7": 70.0, "14": 60.0, "21": 55.0},
            "macd": {"line": 0.5, "signal": 0.25, "histogram": 0.25},
            "ema": {"5": 1.0, "10": 2.0, "12": 3.0, "20": 4.0, "26": 5.0, "30": 6.0, "40": 7.0, "50": 8.0},
            "sma": {"5": 1.5, "10": 2.5, "20": 3.5, "30": 4.5, "40": 5.5, "50": 6.5},
            "stochastic": {"14": {"k": 80.0, "d": 75.0}, "21": {"k": 78.0, "d": 74.0}},
            "adx": {"adx": 25.0, "plus_di": 30.0, "minus_di": 12.0},
        },
        "session_calendar": {
            "asian": True,
            "london": False,
            "new_york": False,
            "london_new_york_overlap": False,
            "minutes_to_asian_open": 120,
            "minutes_to_asian_close": 300,
            "minutes_to_london_open": 60,
            "minutes_to_london_close": 480,
            "minutes_to_new_york_open": 420,
            "minutes_to_new_york_close": 960,
            "day_of_week_sin": 0.5,
            "day_of_week_cos": 0.8660254,
            "week_of_month": 2,
            "month_end_flag": False,
            "quarter_end_flag": False,
            "minutes_to_news": None,
        },
        "market_structure": {
            "last_swing_high": None,
            "last_swing_low": 2620.0,
            "liquidity_pool_buy_side": None,
            "liquidity_pool_sell_side": None,
            "bullish_bos": True,
            "bearish_bos": False,
            "bullish_choch": False,
            "bearish_choch": False,
            "bullish_order_block_low": None,
            "bullish_order_block_high": None,
            "bearish_order_block_low": None,
            "bearish_order_block_high": None,
            "bullish_fvg_low": None,
            "bullish_fvg_high": None,
            "bearish_fvg_low": None,
            "bearish_fvg_high": None,
            "bullish_breaker_count": 2,
            "bearish_breaker_count": 1,
            "bullish_volume_imbalance": True,
            "bearish_volume_imbalance": False,
            "volume_imbalance_score": 1.75,
            "trend": "neutral",
        },
        "cross_asset": {
            "dxy": {
                "5d_corr": -0.2,
                "5d_coint_z": 0.1,
                "5d_beta": -0.3,
                "10d_corr": -0.15,
                "10d_coint_z": 0.2,
                "10d_beta": -0.25,
                "20d_corr": -0.1,
                "20d_coint_z": 0.3,
                "20d_beta": -0.2,
            }
        },
        "regime": {
            "probabilities": {
                "trending": 0.6,
                "mean_reverting": 0.3,
                "volatile": 0.1,
            },
            "regime_duration": 7,
        },
    }


class InferenceFeatureSchemaTests(unittest.TestCase):
    def test_feature_dim_matches_declared_lists(self) -> None:
        self.assertEqual(FEATURE_DIM, len(NUMERIC_FEATURES) + len(BOOLEAN_FEATURES) + 3)
        self.assertEqual(FEATURE_DIM, 107)

    def test_flatten_snapshot_normalizes_aliases(self) -> None:
        flat = flatten_snapshot(_sample_features())
        self.assertEqual(flat["market_structure_trend"], "sideways")
        self.assertEqual(flat["vwap_anchors_session_open_vwap"], 2654.0)
        self.assertEqual(flat["volume_profile_volume_imbalance_score"], 1.75)

    def test_snapshot_to_numpy_encodes_values_in_fixed_positions(self) -> None:
        flat = flatten_snapshot(_sample_features())
        vector = snapshot_to_numpy(flat)
        self.assertEqual(vector.shape, (FEATURE_DIM,))
        self.assertEqual(vector.dtype, np.float32)
        self.assertAlmostEqual(float(vector[vector_index("volume_profile_volume_delta")]), 1.25)
        self.assertAlmostEqual(float(vector[vector_index("market_structure_last_swing_high")]), 0.0)
        self.assertAlmostEqual(float(vector[vector_index("volume_profile_absorption")]), 0.0)
        self.assertAlmostEqual(float(vector[vector_index("market_structure_bullish_bos")]), 1.0)
        self.assertEqual(
            vector[vector_index("market_structure_trend_up"): vector_index("market_structure_trend_sideways") + 1].tolist(),
            [0.0, 0.0, 1.0],
        )

    def test_feature_event_to_numpy_bridges_snapshot(self) -> None:
        snapshot = FeatureSnapshot(
            ts_event_ns=1,
            symbol="XAUUSD",
            timeframe="1h",
            feature_version="fe|test@1.0.0",
            warmup_complete=True,
            missing_count=0,
            features=_sample_features(),
            metadata={},
        )
        feature_event = FeatureEvent.from_snapshot(snapshot)
        vector = feature_event.to_numpy()
        self.assertEqual(vector.shape, (FEATURE_DIM,))
        self.assertAlmostEqual(float(vector[vector_index("regime_probabilities_trending")]), 0.6)

    def test_missing_contract_fields_reports_expected_gaps(self) -> None:
        flat = flatten_snapshot({"market_structure": {"trend": "up"}})
        missing = missing_contract_fields(flat)
        self.assertIn("technical_rsi_14", missing["numeric"])
        self.assertIn("session_calendar_asian", missing["boolean"])
        self.assertEqual(missing["categorical"], [])


if __name__ == "__main__":
    unittest.main()

