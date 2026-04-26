from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class BaseEvent:
    seq_no: int
    ts_event_ns: int

    @property
    def event_type(self) -> str:
        return self.__class__.__name__

    def to_record(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["event_type"] = self.event_type
        return payload


@dataclass(frozen=True, slots=True)
class TickEvent(BaseEvent):
    ts_receive_ns: int
    symbol: str
    bid: float
    ask: float
    last: float
    volume: float
    source: str
    bid_size: float | None = None
    ask_size: float | None = None
    implied_vol: float | None = None


@dataclass(frozen=True, slots=True)
class BarCloseEvent(BaseEvent):
    symbol: str
    timeframe: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    tick_count: int
    vwap: float | None = None


@dataclass(frozen=True, slots=True)
class CrossAssetBarEvent(BarCloseEvent):
    pass


@dataclass(frozen=True, slots=True)
class SessionEvent(BaseEvent):
    symbol: str
    session_name: str
    session_state: str


@dataclass(frozen=True, slots=True)
class NewsEvent(BaseEvent):
    event_name: str
    importance: int
    minutes_to_event: int
    active_window_state: str


@dataclass(frozen=True, slots=True)
class CrossAssetAlignedEvent(BaseEvent):
    symbol: str
    timeframe: str
    bars: Mapping[str, BarCloseEvent] = field(default_factory=dict)


MarketEvent = TickEvent | BarCloseEvent | CrossAssetBarEvent | SessionEvent | NewsEvent | CrossAssetAlignedEvent


EVENT_TYPE_MAP = {
    "TickEvent": TickEvent,
    "BarCloseEvent": BarCloseEvent,
    "CrossAssetBarEvent": CrossAssetBarEvent,
    "SessionEvent": SessionEvent,
    "NewsEvent": NewsEvent,
    "CrossAssetAlignedEvent": CrossAssetAlignedEvent,
}


def event_from_record(record: Mapping[str, Any]) -> MarketEvent:
    payload = dict(record)
    event_type = payload.pop("event_type")
    event_cls = EVENT_TYPE_MAP[event_type]
    return event_cls(**payload)
