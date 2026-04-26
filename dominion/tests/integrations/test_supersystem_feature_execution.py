from __future__ import annotations

import datetime as dt
import sys
from dataclasses import dataclass
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from aphelion.feature_engine.snapshot import build_feature_snapshot
from aphelion.integrations.supersystem.execution_bridge import SuperExecutionStack
from aphelion.integrations.supersystem.feature_bridge import FeatureSnapshotHistoryBridge


@dataclass(frozen=True)
class FakeSignal:
    timestamp_utc: dt.datetime
    model_artifact_id: str
    direction_60m: int
    position_fraction: float

    def is_actionable(self) -> bool:
        return self.direction_60m != 0 and self.position_fraction > 0.0


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
            "dual_source_ratio": 0.8,
        },
        metadata={"dual_source_ratio": 0.8},
    )


def test_feature_bridge_builds_replay_frame() -> None:
    bridge = FeatureSnapshotHistoryBridge(context_len=2)
    bridge.append(_make_snapshot(0, 2350.0))
    bridge.append(_make_snapshot(1, 2351.0))

    frame = bridge.to_dataframe()

    assert frame.height == 2
    assert frame.get_column("symbol").to_list() == ["XAUUSD", "XAUUSD"]
    assert frame.get_column("timeframe").to_list() == ["M1", "M1"]
    assert frame.get_column("close").to_list() == [2350.0, 2351.0]


def test_execution_stack_accepts_contract_compatible_signal() -> None:
    signal = FakeSignal(
        timestamp_utc=dt.datetime(2026, 4, 13, 12, 1, tzinfo=dt.timezone.utc),
        model_artifact_id="dummy-model",
        direction_60m=1,
        position_fraction=0.02,
    )
    stack = SuperExecutionStack(initial_capital=10_000.0)

    fill = stack.submit_signal(
        signal,
        current_price=2351.0,
        atr=5.0,
        timestamp=signal.timestamp_utc,
    )

    assert fill is not None
    closed = stack.mark_price(2371.0, timestamp=signal.timestamp_utc + dt.timedelta(minutes=1))
    assert len(closed) == 1
