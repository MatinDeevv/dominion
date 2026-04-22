"""Canonical home for legacy batch-style feature APIs.

Legacy callers should continue importing through ``aphelion.features.*``.
New code should prefer the event-driven ``aphelion.feature_engine`` surface.
"""

__all__ = [
    "cointegration",
    "cross_impact",
    "engine",
    "halftrend",
    "market_structure",
    "microstructure",
    "mtf",
    "registry",
    "sessions",
    "signature",
    "volume_profile",
    "vwap",
]
