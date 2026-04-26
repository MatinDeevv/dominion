from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from aphelion.feature_engine.engine import FeatureEngine, FeatureEngineConfig
from aphelion.feature_engine.events import BarCloseEvent, CrossAssetBarEvent, SessionEvent
from aphelion.feature_engine.features import CrossAssetRelationshipFeature, RegimeStateFeature, VolumeProfileFeature, VWAPFeature
from aphelion.feature_engine.policies import MissingDataAction, MissingDataPolicy
from aphelion.feature_engine.registry import FeatureRegistry
from aphelion.feature_engine.replay import replay_from_journal


class ReplayAndAlignmentTests(unittest.TestCase):
    def _build_cross_asset_engine(self, *, allow_partial_cross_asset: bool) -> FeatureEngine:
        registry = FeatureRegistry()
        registry.register(
            CrossAssetRelationshipFeature(
                primary_symbol="XAUUSD",
                relationships={"dxy": "DXY"},
                commodity_basket=(),
                day_windows=(1,),
                bars_per_day=1,
                default_timeframe="1h",
            )
        )
        registry.register(RegimeStateFeature(window=3, default_timeframe="1h"))
        return FeatureEngine(
            registry=registry,
            config=FeatureEngineConfig(primary_symbol="XAUUSD", default_timeframe="1h"),
            missing_data_policy=MissingDataPolicy(
                action=MissingDataAction.EMIT_NONE,
                allow_partial_cross_asset=allow_partial_cross_asset,
            ),
        )

    def test_cross_asset_alignment_waits_for_peer_when_partial_disabled(self) -> None:
        engine = self._build_cross_asset_engine(allow_partial_cross_asset=False)

        xau_bar = BarCloseEvent(1, 10_000, "XAUUSD", "1h", 1900, 1905, 1898, 1904, 100, 50, 1902)
        dxy_bar = CrossAssetBarEvent(2, 10_000, "DXY", "1h", 103, 103.1, 102.9, 103.05, 100, 50, 103.0)

        self.assertEqual(engine.on_event(xau_bar), [])
        snapshots = engine.on_event(dxy_bar)
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0].missing_count, 0)
        self.assertIn("cross_asset", snapshots[0].features)

    def test_missing_data_snapshot_emits_none_under_partial_policy(self) -> None:
        engine = self._build_cross_asset_engine(allow_partial_cross_asset=True)
        xau_bar = BarCloseEvent(1, 10_000, "XAUUSD", "1h", 1900, 1905, 1898, 1904, 100, 50, 1902)
        snapshots = engine.on_event(xau_bar)
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0].missing_count, 1)
        self.assertIsNone(snapshots[0].features["cross_asset"])

    def test_replay_is_deterministic(self) -> None:
        registry = FeatureRegistry()
        registry.register(VWAPFeature(default_timeframe="1m"))
        registry.register(VolumeProfileFeature(default_timeframe="1m"))
        config = FeatureEngineConfig(primary_symbol="XAUUSD", default_timeframe="1m")

        records = [
            SessionEvent(1, 1_000, "XAUUSD", "london", "open").to_record(),
            BarCloseEvent(2, 2_000, "XAUUSD", "1m", 100, 101, 99, 100, 50, 10, 100).to_record(),
            BarCloseEvent(3, 3_000, "XAUUSD", "1m", 100, 102, 99, 101, 60, 10, 101).to_record(),
            BarCloseEvent(4, 4_000, "XAUUSD", "1m", 101, 103, 100, 102, 70, 10, 102).to_record(),
        ]

        engine_a = FeatureEngine(registry=registry, config=config)
        engine_b = FeatureEngine(registry=registry, config=config)
        snapshots_a = [snapshot.to_record() for snapshot in replay_from_journal(records, engine_a)]
        snapshots_b = [snapshot.to_record() for snapshot in replay_from_journal(records, engine_b)]

        self.assertEqual(snapshots_a, snapshots_b)

    def test_session_reset_resets_volume_profile_live_path(self) -> None:
        registry = FeatureRegistry()
        registry.register(VolumeProfileFeature(default_timeframe="1m"))
        engine = FeatureEngine(registry=registry, config=FeatureEngineConfig(primary_symbol="XAUUSD", default_timeframe="1m"))

        engine.on_event(SessionEvent(1, 1_000, "XAUUSD", "london", "open"))
        engine.on_event(BarCloseEvent(2, 2_000, "XAUUSD", "1m", 100, 101, 99, 100, 50, 10, 100))
        before_reset = engine.build_latest_snapshot(symbol="XAUUSD", timeframe="1m")

        engine.on_event(SessionEvent(3, 3_000, "XAUUSD", "new_york", "reset"))
        after_reset = engine.build_latest_snapshot(symbol="XAUUSD", timeframe="1m")

        self.assertIsNotNone(before_reset)
        self.assertIsNotNone(after_reset)
        self.assertEqual(after_reset.features["volume_profile"]["cvd"], 0.0)


if __name__ == "__main__":
    unittest.main()

