"""Bridges that compose MT5Pipe, Feature Engine, signals, and execution."""

from .event_pipeline import (
    EventDrivenReplayResult,
    EventDrivenSuperSystem,
    HeuristicSignal,
    HeuristicSignalConfig,
    HeuristicSignalEngine,
)
from .execution_bridge import (
    SignalOrderAdapter,
    SignalOrderAdapterConfig,
    SuperExecutionStack,
)
from .feature_bridge import FeatureSnapshotHistoryBridge

__all__ = [
    "EventDrivenReplayResult",
    "EventDrivenSuperSystem",
    "FeatureSnapshotHistoryBridge",
    "HeuristicSignal",
    "HeuristicSignalConfig",
    "HeuristicSignalEngine",
    "SignalOrderAdapter",
    "SignalOrderAdapterConfig",
    "SuperExecutionStack",
]
