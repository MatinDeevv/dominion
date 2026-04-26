from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable, Sequence, Type

from .events import MarketEvent
from .features.base import BaseFeature, CrossAssetFeature


@dataclass(slots=True)
class FeatureRegistry:
    _features: list[BaseFeature] = field(default_factory=list)
    _by_event_type: dict[Type[object], list[BaseFeature]] = field(default_factory=lambda: defaultdict(list))

    def register(self, feature: BaseFeature) -> None:
        self._features.append(feature)
        for event_type in feature.event_types:
            self._by_event_type[event_type].append(feature)

    def register_many(self, features: Iterable[BaseFeature]) -> None:
        for feature in features:
            self.register(feature)

    @property
    def features(self) -> Sequence[BaseFeature]:
        return tuple(self._features)

    def features_for_event(self, event: MarketEvent) -> list[BaseFeature]:
        selected: list[BaseFeature] = []
        for event_type, features in self._by_event_type.items():
            if isinstance(event, event_type):
                selected.extend(feature for feature in features if feature.enabled)
        selected.sort(key=lambda feature: feature.name)
        return selected

    def feature_names(self) -> list[str]:
        return [feature.name for feature in self._features]

    def cross_asset_features(self) -> list[CrossAssetFeature]:
        return [feature for feature in self._features if isinstance(feature, CrossAssetFeature) and feature.enabled]

    def required_cross_asset_symbols(self) -> set[str]:
        required: set[str] = set()
        for feature in self.cross_asset_features():
            required.update(feature.required_symbols)
        return required

