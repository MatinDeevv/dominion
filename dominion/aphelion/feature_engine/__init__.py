"""Journal-first feature engine for deterministic live/replay parity."""

from .snapshot import FeatureSnapshot, build_feature_snapshot, flatten_feature_snapshot

__all__ = [
    "BarEvent",
    "BarCloseEvent",
    "CrossAssetAlignedEvent",
    "CrossAssetBarEvent",
    "FeatureEngine",
    "FeatureEngineConfig",
    "LegacyFeatureEngine",
    "FeatureSnapshot",
    "NewsEvent",
    "SessionEvent",
    "TickEvent",
    "build_default_registry",
    "build_feature_snapshot",
    "flatten_feature_snapshot",
]


def __getattr__(name: str):
    if name in {"FeatureEngine", "FeatureEngineConfig"}:
        from .engine import FeatureEngine, FeatureEngineConfig

        return {"FeatureEngine": FeatureEngine, "FeatureEngineConfig": FeatureEngineConfig}[name]

    if name == "LegacyFeatureEngine":
        from .legacy_runtime import LegacyFeatureEngine

        return LegacyFeatureEngine

    if name == "build_default_registry":
        from .defaults import build_default_registry

        return build_default_registry

    if name in {
        "BarCloseEvent",
        "CrossAssetAlignedEvent",
        "CrossAssetBarEvent",
        "NewsEvent",
        "SessionEvent",
        "TickEvent",
    }:
        from .events import (
            BarCloseEvent,
            CrossAssetAlignedEvent,
            CrossAssetBarEvent,
            NewsEvent,
            SessionEvent,
            TickEvent,
        )

        event_exports = {
            "BarCloseEvent": BarCloseEvent,
            "CrossAssetAlignedEvent": CrossAssetAlignedEvent,
            "CrossAssetBarEvent": CrossAssetBarEvent,
            "NewsEvent": NewsEvent,
            "SessionEvent": SessionEvent,
            "TickEvent": TickEvent,
        }
        return event_exports[name]

    if name == "BarEvent":
        from .events import BarCloseEvent

        return BarCloseEvent

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
