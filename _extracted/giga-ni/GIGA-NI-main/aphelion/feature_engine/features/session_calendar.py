from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Any

from ..events import BarCloseEvent, NewsEvent, SessionEvent
from ..utils import ns_to_datetime
from .base import SessionFeature, FeatureContext


def compute_session_flags(current_dt: datetime, session_hours: dict[str, tuple[int, int]]) -> dict[str, bool]:
    current_hour = current_dt.hour
    flags = {
        name: start <= current_hour < end
        for name, (start, end) in session_hours.items()
    }
    flags["london_new_york_overlap"] = flags.get("london", False) and flags.get("new_york", False)
    return flags


def compute_time_to_session_open_close(
    current_dt: datetime,
    session_hours: dict[str, tuple[int, int]],
) -> dict[str, int]:
    values: dict[str, int] = {}
    today = current_dt.date()
    for name, (start_hour, end_hour) in session_hours.items():
        start_dt = datetime(today.year, today.month, today.day, start_hour, tzinfo=current_dt.tzinfo)
        end_dt = datetime(today.year, today.month, today.day, end_hour, tzinfo=current_dt.tzinfo)
        if end_dt <= start_dt:
            end_dt += timedelta(days=1)
        if start_dt < current_dt:
            start_dt += timedelta(days=1)
        if end_dt < current_dt:
            end_dt += timedelta(days=1)
        values[f"minutes_to_{name}_open"] = int((start_dt - current_dt).total_seconds() // 60)
        values[f"minutes_to_{name}_close"] = int((end_dt - current_dt).total_seconds() // 60)
    return values


def compute_day_of_week_encoding(current_dt: datetime) -> dict[str, float]:
    day = current_dt.weekday()
    angle = (2.0 * 3.141592653589793 * day) / 7.0
    return {"day_of_week_sin": __import__("math").sin(angle), "day_of_week_cos": __import__("math").cos(angle)}


def compute_week_of_month(current_dt: datetime) -> int:
    return ((current_dt.day - 1) // 7) + 1


def compute_news_proximity(news_state: NewsEvent | None) -> dict[str, Any]:
    if news_state is None:
        return {"minutes_to_news": None, "news_importance": None, "news_active_window": None}
    return {
        "minutes_to_news": news_state.minutes_to_event,
        "news_importance": news_state.importance,
        "news_active_window": news_state.active_window_state,
    }


def compute_month_end_flag(current_dt: datetime) -> bool:
    last_day = calendar.monthrange(current_dt.year, current_dt.month)[1]
    return current_dt.day >= last_day - 1


def compute_quarter_end_flag(current_dt: datetime) -> bool:
    return current_dt.month in {3, 6, 9, 12} and compute_month_end_flag(current_dt)


class SessionCalendarFeature(SessionFeature):
    def __init__(
        self,
        *,
        name: str = "session_calendar",
        version: str = "1.0.0",
        timezone_name: str = "UTC",
        default_timeframe: str = "1m",
    ) -> None:
        super().__init__(name=name, version=version, default_timeframe=default_timeframe, warmup_periods=1)
        self.timezone_name = timezone_name
        self.session_hours = {
            "asian": (0, 8),
            "london": (7, 16),
            "new_york": (13, 22),
        }

    def initialize_state(self) -> dict[str, Any]:
        return {
            "last_session_event": None,
            "last_news_event": None,
            "values": {},
        }

    def update(self, event: SessionEvent | NewsEvent | BarCloseEvent, state: dict[str, Any], context: FeatureContext) -> None:
        if isinstance(event, SessionEvent):
            state["last_session_event"] = {"session_name": event.session_name, "session_state": event.session_state}
            return
        if isinstance(event, NewsEvent):
            state["last_news_event"] = event
            return
        if not isinstance(event, BarCloseEvent):
            return

        dt = ns_to_datetime(event.ts_event_ns, tz=ZoneInfo(self.timezone_name))
        flags = compute_session_flags(dt, self.session_hours)
        session_event = state["last_session_event"] or {}
        state["values"] = {
            **flags,
            **compute_time_to_session_open_close(dt, self.session_hours),
            **compute_day_of_week_encoding(dt),
            **compute_news_proximity(state["last_news_event"]),
            "week_of_month": compute_week_of_month(dt),
            "month_end_flag": compute_month_end_flag(dt),
            "quarter_end_flag": compute_quarter_end_flag(dt),
            "session_name": session_event.get("session_name"),
            "session_state": session_event.get("session_state"),
        }

    def ready(self, state: dict[str, Any]) -> bool:
        return bool(state["values"])

    def value(self, state: dict[str, Any]) -> dict[str, Any]:
        return dict(state["values"])

