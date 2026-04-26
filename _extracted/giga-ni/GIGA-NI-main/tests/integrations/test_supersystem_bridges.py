from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pytest

torch = pytest.importorskip("torch")

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from aphelion.feature_engine.snapshot import build_feature_snapshot
from aphelion.integrations.supersystem.execution_bridge import SuperExecutionStack
from aphelion.integrations.supersystem.feature_bridge import FeatureSnapshotHistoryBridge
from aphelion.integrations.supersystem.signal_bridge import NeuralSignalEngine
from machinelearning.models import ModelOutput
from machinelearning.signal.publisher import SignalPublisher
from machinelearning.signal.sizing import KellyPositionSizer


class _StubCalibrator:
    empirical_coverage = 0.9

    def predict(self, lower: float, upper: float) -> tuple[float, float]:
        return lower, upper


class _DummyModel:
    def __call__(self, batch: dict[str, torch.Tensor]) -> ModelOutput:
        direction = torch.tensor([[0.1, 0.2, 2.6]], dtype=torch.float32)
        flat_three = torch.tensor([[0.2, 0.2, 0.6]], dtype=torch.float32)
        returns = torch.tensor([[0.01, 0.02, 0.04, 0.06, 0.08]], dtype=torch.float32)
        aux = torch.tensor([[0.01]], dtype=torch.float32)
        return ModelOutput(
            direction_logits={
                "5m": flat_three,
                "15m": flat_three,
                "60m": direction,
                "240m": flat_three,
            },
            tb_logits={
                "5m": flat_three,
                "15m": flat_three,
                "60m": flat_three,
                "240m": flat_three,
            },
            return_preds={
                "5m": returns,
                "15m": returns,
                "60m": returns,
                "240m": returns,
            },
            mae_preds={
                "5m": aux,
                "15m": aux,
                "60m": aux,
                "240m": aux,
            },
            mfe_preds={
                "5m": aux,
                "15m": aux,
                "60m": aux,
                "240m": aux,
            },
        )


def _prepare_batch(history_frame):
    assert history_frame.height >= 2
    return {
        "past_features": torch.zeros((1, 2, 4), dtype=torch.float32),
        "future_known": torch.zeros((1, 2, 2), dtype=torch.float32),
        "static": torch.zeros((1, 1), dtype=torch.float32),
        "mask": torch.ones((1, 2), dtype=torch.bool),
        "time_idx": torch.tensor([history_frame.height - 1], dtype=torch.int64),
    }


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
            "disagreement_pressure_bps": 0.5,
        },
        metadata={"dual_source_ratio": 0.8, "disagreement_pressure_bps": 0.5},
    )


def test_history_bridge_translates_feature_snapshot_to_ml_frame() -> None:
    bridge = FeatureSnapshotHistoryBridge(context_len=2)
    bridge.append(_make_snapshot(0, 2350.0))
    bridge.append(_make_snapshot(1, 2351.0))

    frame = bridge.to_dataframe()

    assert frame.height == 2
    assert frame.get_column("symbol").to_list() == ["XAUUSD", "XAUUSD"]
    assert frame.get_column("timeframe").to_list() == ["M1", "M1"]
    assert frame.get_column("close").to_list() == [2350.0, 2351.0]
    assert bridge.is_ready() is True


def test_neural_signal_engine_emits_actionable_signal_record() -> None:
    bridge = FeatureSnapshotHistoryBridge(context_len=2)
    publisher = SignalPublisher(
        model_artifact_id="dummy-tft",
        calibrator=_StubCalibrator(),
        sizer=KellyPositionSizer(max_kelly=0.25, kelly_fraction=0.25),
    )
    engine = NeuralSignalEngine(
        history=bridge,
        batch_preparer=_prepare_batch,
        model=_DummyModel(),
        publisher=publisher,
        actionable_only=True,
    )

    assert engine.consume(_make_snapshot(0, 2350.0)) is None
    signal = engine.consume(_make_snapshot(1, 2351.0))

    assert signal is not None
    assert signal.symbol == "XAUUSD"
    assert signal.direction_60m == 1
    assert signal.is_actionable() is True


def test_execution_stack_routes_signal_into_paper_executor() -> None:
    bridge = FeatureSnapshotHistoryBridge(context_len=2)
    publisher = SignalPublisher(
        model_artifact_id="dummy-tft",
        calibrator=_StubCalibrator(),
        sizer=KellyPositionSizer(max_kelly=0.25, kelly_fraction=0.25),
    )
    engine = NeuralSignalEngine(
        history=bridge,
        batch_preparer=_prepare_batch,
        model=_DummyModel(),
        publisher=publisher,
        actionable_only=True,
    )
    engine.consume(_make_snapshot(0, 2350.0))
    signal = engine.consume(_make_snapshot(1, 2351.0))
    assert signal is not None

    stack = SuperExecutionStack(initial_capital=10_000.0)
    fill = stack.submit_signal(
        signal,
        current_price=2351.0,
        atr=5.0,
        timestamp=signal.timestamp_utc,
    )

    assert fill is not None
    assert len(stack.portfolio._open_positions) == 1

    closed = stack.mark_price(2371.0, timestamp=signal.timestamp_utc + dt.timedelta(minutes=1))
    assert len(closed) == 1
