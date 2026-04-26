from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Sequence, Type

from ..events import BarCloseEvent, CrossAssetAlignedEvent, MarketEvent, NewsEvent, SessionEvent, TickEvent
from ..utils import recursive_restore, recursive_serialize


@dataclass(frozen=True, slots=True)
class FeatureScope:
    symbol: str
    timeframe: str


@dataclass(slots=True)
class FeatureContext:
    state_store: object
    primary_symbol: str
    event: MarketEvent
    default_timeframe: str
    time_zone: str = "UTC"

    def latest_tick(self, symbol: str):
        return self.state_store.latest_tick(symbol)

    def latest_bar(self, symbol: str, timeframe: str):
        return self.state_store.latest_bar(symbol, timeframe)

    def current_session(self, symbol: str):
        return self.state_store.sessions.get(symbol)

    def active_news(self):
        return self.state_store.active_news


class BaseFeature(ABC):
    category = "base"
    event_types: Sequence[Type[object]] = ()

    def __init__(
        self,
        *,
        name: str,
        version: str,
        enabled: bool = True,
        default_timeframe: str = "1m",
        warmup_periods: int = 1,
    ) -> None:
        self.name = name
        self.version = version
        self.enabled = enabled
        self.default_timeframe = default_timeframe
        self.warmup_periods = warmup_periods

    def handles(self, event: MarketEvent) -> bool:
        return any(isinstance(event, event_type) for event_type in self.event_types)

    def supports_timeframe(self, timeframe: str) -> bool:
        return self.default_timeframe == timeframe

    def scope(self, event: MarketEvent, context: FeatureContext) -> FeatureScope:
        symbol = getattr(event, "symbol", context.primary_symbol)
        timeframe = getattr(event, "timeframe", self.default_timeframe)
        return FeatureScope(symbol=symbol, timeframe=timeframe)

    @abstractmethod
    def initialize_state(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def update(self, event: MarketEvent, state: dict[str, Any], context: FeatureContext) -> None:
        raise NotImplementedError

    @abstractmethod
    def ready(self, state: dict[str, Any]) -> bool:
        raise NotImplementedError

    @abstractmethod
    def value(self, state: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def reset(self, state: dict[str, Any], reason: str = "manual") -> None:
        state.clear()
        state.update(self.initialize_state())
        state["last_reset_reason"] = reason

    def serialize_state(self, state: dict[str, Any]) -> dict[str, Any]:
        return recursive_serialize(state)

    def restore_state(self, payload: dict[str, Any]) -> dict[str, Any]:
        return recursive_restore(payload)


class TickFeature(BaseFeature):
    category = "tick"
    event_types = (TickEvent,)


class BarFeature(BaseFeature):
    category = "bar"
    event_types = (BarCloseEvent,)


class SessionFeature(BaseFeature):
    category = "session"
    event_types = (SessionEvent, NewsEvent, BarCloseEvent)


class CrossAssetFeature(BaseFeature):
    category = "cross_asset"
    event_types = (CrossAssetAlignedEvent,)
    required_symbols: set[str]

    def __init__(self, *, required_symbols: set[str], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.required_symbols = required_symbols


class RegimeFeature(BaseFeature):
    category = "regime"
    event_types = (BarCloseEvent,)
