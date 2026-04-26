"""Workspace-level replay runner that composes the four APHELION projects."""

from __future__ import annotations

from dataclasses import dataclass

from aphelion.feature_engine.integrations.mt5pipe import MT5PipeReplayConfig, replay_mt5pipe_into_engine

from .execution_bridge import SuperExecutionStack
from .feature_bridge import extract_market_context
from .signal_bridge import NeuralSignalEngine


@dataclass(frozen=True)
class SuperSystemReplayResult:
    snapshots_processed: int
    actionable_signals: int
    fills: int
    closed_positions: int
    final_equity: float


class SuperSystemReplayRunner:
    """Replay MT5Pipe data through features, neural signals, and paper execution."""

    def __init__(
        self,
        signal_engine: NeuralSignalEngine,
        execution_stack: SuperExecutionStack | None = None,
    ) -> None:
        self.signal_engine = signal_engine
        self.execution_stack = execution_stack or SuperExecutionStack()

    def replay(self, replay_config: MT5PipeReplayConfig) -> SuperSystemReplayResult:
        snapshots = replay_mt5pipe_into_engine(replay_config)
        actionable_signals = 0
        fills = 0

        for snapshot in snapshots:
            context = extract_market_context(snapshot)
            current_price = context["current_price"]
            if current_price is None:
                continue

            self.execution_stack.mark_price(
                current_price,
                timestamp=context["timestamp_utc"],
            )

            signal = self.signal_engine.consume(snapshot)
            if signal is None:
                continue

            actionable_signals += 1
            fill = self.execution_stack.submit_signal(
                signal,
                current_price=current_price,
                atr=context["atr"],
                timestamp=context["timestamp_utc"],
            )
            if fill is not None:
                fills += 1

        return SuperSystemReplayResult(
            snapshots_processed=len(snapshots),
            actionable_signals=actionable_signals,
            fills=fills,
            closed_positions=len(self.execution_stack.closed_positions),
            final_equity=self.execution_stack.portfolio.equity,
        )


__all__ = [
    "SuperSystemReplayResult",
    "SuperSystemReplayRunner",
]
