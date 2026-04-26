"""Bridge rolling feature snapshots into calibrated neural trading signals."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol

import polars as pl

from aphelion.feature_engine.snapshot import FeatureSnapshot
from machinelearning.models import ModelOutput
from machinelearning.signal import SignalPublisher, SignalRecord

from .feature_bridge import FeatureSnapshotHistoryBridge


class BatchPreparer(Protocol):
    def __call__(self, history_frame: pl.DataFrame) -> dict[str, Any]:
        """Build the model batch from the rolling history dataframe."""


class ModelRunner(Protocol):
    def __call__(self, batch: dict[str, Any]) -> ModelOutput:
        """Run the model and return the shared output contract."""


class RegimeProvider(Protocol):
    def __call__(self, history_frame: pl.DataFrame, output: ModelOutput, snapshot: FeatureSnapshot) -> Any:
        """Infer the regime state used by the signal publisher."""


def default_regime_provider(
    history_frame: pl.DataFrame,
    output: ModelOutput,
    snapshot: FeatureSnapshot,
) -> dict[str, Any]:
    return {
        "regime_probs": [0.25, 0.25, 0.25, 0.25],
        "regime_names": ("trending", "mean_reverting", "volatile", "quiet"),
    }


@dataclass
class NeuralSignalEngine:
    """Compose history building, batch prep, model inference, and signal publishing."""

    history: FeatureSnapshotHistoryBridge
    batch_preparer: BatchPreparer
    model: ModelRunner
    publisher: SignalPublisher
    regime_provider: RegimeProvider = default_regime_provider
    actionable_only: bool = True

    def consume(self, snapshot: FeatureSnapshot) -> SignalRecord | None:
        self.history.append(snapshot)
        if not snapshot.warmup_complete:
            return None
        if not self.history.is_ready():
            return None

        history_frame = self.history.to_dataframe()
        batch = self.batch_preparer(history_frame)
        output = self.model(batch)
        regime_state = self.regime_provider(history_frame, output, snapshot)
        signal = self.publisher.publish(output, regime_state, self.history.latest_bar_metadata())

        if self.actionable_only and not signal.is_actionable():
            return None
        return signal


__all__ = [
    "BatchPreparer",
    "ModelRunner",
    "NeuralSignalEngine",
    "RegimeProvider",
    "default_regime_provider",
]
