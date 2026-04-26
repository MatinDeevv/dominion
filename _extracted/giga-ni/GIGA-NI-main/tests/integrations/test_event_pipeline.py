from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pytest

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from aphelion.core.config import EventTopic
from aphelion.feature_engine.snapshot import build_feature_snapshot
from aphelion.integrations.supersystem import EventDrivenSuperSystem, HeuristicSignalConfig, HeuristicSignalEngine
from aphelion.integrations.supersystem.execution_bridge import SuperExecutionStack


def _make_snapshot(minute_offset: int, close: float) -> object:
    ts = dt.datetime(2026, 4, 13, 12, minute_offset, tzinfo=dt.timezone.utc)
    return build_feature_snapshot(
        ts_event_ns=int(ts.timestamp() * 1_000_000_000),
        symbol="XAUUSD",
        timeframe="1m",
        feature_version="test",
        warmup_complete=True,
        missing_count=0,
        features={
            "close": close,
            "atr": 5.0,
            "dual_source_ratio": 0.9,
        },
        metadata={"dual_source_ratio": 0.9},
    )


@pytest.mark.asyncio
async def test_event_driven_pipeline_publishes_feature_signal_and_order_events() -> None:
    engine = HeuristicSignalEngine(config=HeuristicSignalConfig(context_len=3, lookback_bars=1, min_abs_return=0.0001))
    system = EventDrivenSuperSystem(
        signal_engine=engine,
        execution_stack=SuperExecutionStack(initial_capital=10_000.0),
    )

    result = await system.run_snapshots(
        [
            _make_snapshot(0, 2350.0),
            _make_snapshot(1, 2352.0),
            _make_snapshot(2, 2354.0),
            _make_snapshot(3, 2376.0),
        ]
    )

    history = system.event_bus.get_history()
    topics = [event.topic for event in history]

    assert result.snapshots_processed == 4
    assert result.features_emitted == 4
    assert result.signals_generated >= 1
    assert result.decisions_published >= 1
    assert result.fills >= 1
    assert EventTopic.FEATURE in topics
    assert EventTopic.SIGNAL in topics
    assert EventTopic.DECISION in topics
    assert EventTopic.ORDER in topics
