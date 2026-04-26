"""Compatibility exports for the legacy feature-engine path."""

__all__ = ["FeatureEngine"]


def __getattr__(name: str):
    if name == "FeatureEngine":
        from aphelion.features.engine import FeatureEngine

        return FeatureEngine
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
