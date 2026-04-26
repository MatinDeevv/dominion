"""Deprecated compatibility namespace for legacy feature imports."""

from __future__ import annotations

import warnings

__all__ = ["FeatureEngine"]


def __getattr__(name: str):
    warnings.warn(
        "aphelion.features is deprecated. Use aphelion.feature_engine instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    if name == "FeatureEngine":
        from aphelion.features.engine import FeatureEngine

        return FeatureEngine
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
