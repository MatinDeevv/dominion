from __future__ import annotations

from aphelion.feature_engine.engine import FeatureEngine, FeatureEngineConfig
from aphelion.feature_engine.events import BarCloseEvent
from aphelion.feature_engine.features import TechnicalFeature
from aphelion.feature_engine.registry import FeatureRegistry


def test_canonical_feature_engine_emits_bar_snapshot() -> None:
    registry = FeatureRegistry()
    registry.register(TechnicalFeature(default_timeframe="1m"))
    engine = FeatureEngine(
        registry=registry,
        config=FeatureEngineConfig(primary_symbol="XAUUSD", default_timeframe="1m"),
    )

    snapshots = []
    for seq in range(1, 220):
        close = 1900.0 + seq
        bar = BarCloseEvent(
            seq_no=seq,
            ts_event_ns=seq * 1_000_000_000,
            symbol="XAUUSD",
            timeframe="1m",
            open=close - 1,
            high=close + 1,
            low=close - 2,
            close=close,
            volume=100.0,
            tick_count=50,
            vwap=close,
        )
        snapshots = engine.on_event(bar)

    assert snapshots
    snapshot = snapshots[-1]
    assert snapshot.symbol == "XAUUSD"
    assert snapshot.timeframe == "1m"
    assert "technical" in snapshot.features
