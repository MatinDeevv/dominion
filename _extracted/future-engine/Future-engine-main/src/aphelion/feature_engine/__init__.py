"""Journal-first feature engine for deterministic live/replay parity."""

from .defaults import build_default_registry
from .engine import FeatureEngine, FeatureEngineConfig
from .events import (
    BarCloseEvent,
    CrossAssetAlignedEvent,
    CrossAssetBarEvent,
    NewsEvent,
    SessionEvent,
    TickEvent,
)
from .snapshot import FeatureSnapshot, build_feature_snapshot, flatten_feature_snapshot

BarEvent = BarCloseEvent

__all__ = [
    "BarEvent",
    "BarCloseEvent",
    "CrossAssetAlignedEvent",
    "CrossAssetBarEvent",
    "FeatureEngine",
    "FeatureEngineConfig",
    "FeatureSnapshot",
    "NewsEvent",
    "SessionEvent",
    "TickEvent",
    "build_default_registry",
    "build_feature_snapshot",
    "flatten_feature_snapshot",
]
