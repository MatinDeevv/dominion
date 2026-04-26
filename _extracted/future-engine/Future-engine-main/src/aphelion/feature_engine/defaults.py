from __future__ import annotations

from .features import (
    CrossAssetRelationshipFeature,
    MarketStructureFeature,
    MicrostructureFeature,
    RegimeStateFeature,
    SessionCalendarFeature,
    TechnicalFeature,
    VolumeProfileFeature,
    VWAPFeature,
)
from .registry import FeatureRegistry


def build_default_registry(
    *,
    primary_symbol: str = "XAUUSD",
    default_timeframe: str = "1m",
    structure_timeframe: str = "15m",
    cross_asset_timeframe: str = "1h",
    include_btc: bool = False,
) -> FeatureRegistry:
    registry = FeatureRegistry()
    registry.register_many(
        [
            MicrostructureFeature(default_timeframe=default_timeframe),
            VolumeProfileFeature(default_timeframe=default_timeframe),
            VWAPFeature(default_timeframe=default_timeframe),
            TechnicalFeature(default_timeframe=default_timeframe),
            SessionCalendarFeature(default_timeframe=default_timeframe),
            MarketStructureFeature(default_timeframe=structure_timeframe),
            CrossAssetRelationshipFeature(
                primary_symbol=primary_symbol,
                include_btc=include_btc,
                default_timeframe=cross_asset_timeframe,
                bars_per_day=24,
            ),
            RegimeStateFeature(default_timeframe=cross_asset_timeframe),
        ]
    )
    return registry

