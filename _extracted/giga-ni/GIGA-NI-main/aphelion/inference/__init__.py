"""Inference-side feature vector contracts and adapters."""

from .events import FeatureEvent
from .feature_schema import (
    BOOLEAN_FEATURES,
    FEATURE_DIM,
    NUMERIC_FEATURES,
    TREND_ENCODING,
    flatten_snapshot,
    snapshot_to_numpy,
    vector_index,
)

__all__ = [
    "BOOLEAN_FEATURES",
    "FEATURE_DIM",
    "FeatureEvent",
    "NUMERIC_FEATURES",
    "TREND_ENCODING",
    "flatten_snapshot",
    "snapshot_to_numpy",
    "vector_index",
]

