from __future__ import annotations

from collections import deque
from typing import Any

from ..events import BarCloseEvent, SessionEvent, TickEvent
from ..utils import mean, safe_div, sign
from .base import BaseFeature, FeatureContext


def compute_volume_delta(price_change: float, volume: float) -> float:
    return sign(price_change) * volume


def compute_cvd(previous_cvd: float, volume_delta: float) -> float:
    return previous_cvd + volume_delta


def compute_poc(profile: dict[float, float]) -> float | None:
    if not profile:
        return None
    return max(profile.items(), key=lambda item: item[1])[0]


def compute_vah_val(profile: dict[float, float], value_area_fraction: float = 0.70) -> tuple[float | None, float | None]:
    if not profile:
        return None, None
    total_volume = sum(profile.values())
    if total_volume == 0:
        return None, None
    poc = compute_poc(profile)
    prices = sorted(profile)
    indexed = {price: index for index, price in enumerate(prices)}
    poc_index = indexed[poc]
    selected = {poc}
    cumulative = profile[poc]
    left = poc_index - 1
    right = poc_index + 1
    while cumulative / total_volume < value_area_fraction and (left >= 0 or right < len(prices)):
        left_volume = profile[prices[left]] if left >= 0 else -1.0
        right_volume = profile[prices[right]] if right < len(prices) else -1.0
        if right_volume >= left_volume:
            selected.add(prices[right])
            cumulative += right_volume
            right += 1
        else:
            selected.add(prices[left])
            cumulative += left_volume
            left -= 1
    return max(selected), min(selected)


def detect_delta_divergence(price_change: float, cvd_change: float) -> bool:
    return sign(price_change) != 0 and sign(price_change) != sign(cvd_change)


def detect_absorption(price_range: float, volume: float, average_range: float, average_volume: float) -> bool:
    if average_range == 0 or average_volume == 0:
        return False
    return volume > average_volume * 1.5 and price_range < average_range * 0.6


class VolumeProfileFeature(BaseFeature):
    category = "volume_profile"
    event_types = (TickEvent, BarCloseEvent, SessionEvent)

    def __init__(
        self,
        *,
        name: str = "volume_profile",
        version: str = "1.0.0",
        price_bin_size: float = 0.5,
        default_timeframe: str = "1m",
        warmup_periods: int = 10,
    ) -> None:
        super().__init__(name=name, version=version, default_timeframe=default_timeframe, warmup_periods=warmup_periods)
        self.price_bin_size = price_bin_size

    def initialize_state(self) -> dict[str, Any]:
        return {
            "profile": {},
            "delta_profile": {},
            "cvd": 0.0,
            "last_price": None,
            "last_bar_close": None,
            "last_bar_cvd": 0.0,
            "range_window": deque(maxlen=50),
            "volume_window": deque(maxlen=50),
            "tick_count": 0,
            "session_name": None,
            "values": {},
        }

    def update(self, event: TickEvent | BarCloseEvent | SessionEvent, state: dict[str, Any], context: FeatureContext) -> None:
        if isinstance(event, SessionEvent) and event.session_state in {"open", "reset"}:
            state["profile"] = {}
            state["delta_profile"] = {}
            state["cvd"] = 0.0
            state["last_bar_cvd"] = 0.0
            state["session_name"] = event.session_name
            return

        if isinstance(event, TickEvent):
            state["tick_count"] += 1
            reference_price = state["last_price"] if state["last_price"] is not None else event.last
            volume_delta = compute_volume_delta(event.last - reference_price, event.volume)
            state["cvd"] = compute_cvd(state["cvd"], volume_delta)
            price_bin = round(event.last / self.price_bin_size) * self.price_bin_size
            state["profile"][price_bin] = state["profile"].get(price_bin, 0.0) + event.volume
            state["delta_profile"][price_bin] = state["delta_profile"].get(price_bin, 0.0) + volume_delta
            state["last_price"] = event.last

        if isinstance(event, BarCloseEvent):
            typical_price = event.vwap if event.vwap is not None else (event.high + event.low + event.close) / 3.0
            state["profile"][round(typical_price / self.price_bin_size) * self.price_bin_size] = (
                state["profile"].get(round(typical_price / self.price_bin_size) * self.price_bin_size, 0.0) + event.volume
            )
            state["range_window"].append(event.high - event.low)
            state["volume_window"].append(event.volume)
            price_change = 0.0 if state["last_bar_close"] is None else event.close - state["last_bar_close"]
            cvd_change = state["cvd"] - state["last_bar_cvd"]
            poc = compute_poc(state["profile"])
            vah, val = compute_vah_val(state["profile"])
            state["values"] = {
                "volume_delta": cvd_change,
                "cvd": state["cvd"],
                "poc": poc,
                "vah": vah,
                "val": val,
                "delta_divergence": detect_delta_divergence(price_change, cvd_change),
                "absorption": detect_absorption(
                    event.high - event.low,
                    event.volume,
                    mean(list(state["range_window"])),
                    mean(list(state["volume_window"])),
                ),
            }
            state["last_bar_close"] = event.close
            state["last_bar_cvd"] = state["cvd"]

    def ready(self, state: dict[str, Any]) -> bool:
        return state["tick_count"] >= self.warmup_periods or bool(state["values"])

    def value(self, state: dict[str, Any]) -> dict[str, Any]:
        return dict(state["values"])

