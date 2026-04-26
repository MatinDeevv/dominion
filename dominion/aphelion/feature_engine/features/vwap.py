from __future__ import annotations

from collections import deque
from typing import Any

from ..events import BarCloseEvent, SessionEvent
from ..utils import WeightedRunningStats, safe_div
from .base import BaseFeature, FeatureContext


def compute_session_vwap(price_volume: float, volume: float) -> float:
    return safe_div(price_volume, volume)


def compute_anchored_vwap(price_volume: float, volume: float) -> float:
    return safe_div(price_volume, volume)


def compute_rolling_vwap(window: list[tuple[float, float]]) -> float:
    numerator = sum(price * volume for price, volume in window)
    denominator = sum(volume for _, volume in window)
    return safe_div(numerator, denominator)


def compute_vwap_bands(vwap: float, weighted_std: float, multiplier: float) -> tuple[float, float]:
    return vwap + (weighted_std * multiplier), vwap - (weighted_std * multiplier)


class VWAPFeature(BaseFeature):
    category = "vwap"
    event_types = (BarCloseEvent, SessionEvent)

    def __init__(
        self,
        *,
        name: str = "vwap",
        version: str = "1.0.0",
        rolling_window: int = 20,
        default_timeframe: str = "1m",
    ) -> None:
        super().__init__(name=name, version=version, default_timeframe=default_timeframe, warmup_periods=rolling_window)
        self.rolling_window = rolling_window

    def initialize_state(self) -> dict[str, Any]:
        return {
            "session_pv": 0.0,
            "session_volume": 0.0,
            "session_stats": WeightedRunningStats(),
            "rolling": deque(maxlen=self.rolling_window),
            "anchors": {},
            "values": {},
        }

    def update(self, event: BarCloseEvent | SessionEvent, state: dict[str, Any], context: FeatureContext) -> None:
        if isinstance(event, SessionEvent) and event.session_state in {"open", "reset"}:
            state["session_pv"] = 0.0
            state["session_volume"] = 0.0
            state["session_stats"] = WeightedRunningStats()
            state["anchors"] = {
                f"session_{event.session_name.lower()}": {"pv": 0.0, "volume": 0.0, "stats": WeightedRunningStats()}
            }
            return

        if not isinstance(event, BarCloseEvent):
            return

        typical_price = event.vwap if event.vwap is not None else (event.high + event.low + event.close) / 3.0
        volume = max(event.volume, 0.0)
        state["session_pv"] += typical_price * volume
        state["session_volume"] += volume
        state["session_stats"].update(typical_price, volume)
        state["rolling"].append((typical_price, volume))

        if not state["anchors"]:
            state["anchors"]["session_open"] = {"pv": 0.0, "volume": 0.0, "stats": WeightedRunningStats()}
        for anchor_state in state["anchors"].values():
            anchor_state["pv"] += typical_price * volume
            anchor_state["volume"] += volume
            anchor_state["stats"].update(typical_price, volume)

        session_vwap = compute_session_vwap(state["session_pv"], state["session_volume"])
        rolling_vwap = compute_rolling_vwap(list(state["rolling"]))
        session_band_1_up, session_band_1_down = compute_vwap_bands(session_vwap, state["session_stats"].std(), 1.0)
        session_band_2_up, session_band_2_down = compute_vwap_bands(session_vwap, state["session_stats"].std(), 2.0)

        anchored_payload: dict[str, Any] = {}
        for anchor_name, anchor_state in state["anchors"].items():
            anchored_vwap = compute_anchored_vwap(anchor_state["pv"], anchor_state["volume"])
            band_up, band_down = compute_vwap_bands(anchored_vwap, anchor_state["stats"].std(), 1.0)
            anchored_payload[anchor_name] = {
                "vwap": anchored_vwap,
                "band_up_1": band_up,
                "band_down_1": band_down,
            }

        state["values"] = {
            "session_vwap": session_vwap,
            "rolling_vwap": rolling_vwap,
            "band_up_1": session_band_1_up,
            "band_down_1": session_band_1_down,
            "band_up_2": session_band_2_up,
            "band_down_2": session_band_2_down,
            "anchors": anchored_payload,
        }

    def ready(self, state: dict[str, Any]) -> bool:
        return len(state["rolling"]) >= min(self.rolling_window, 5)

    def value(self, state: dict[str, Any]) -> dict[str, Any]:
        return dict(state["values"])

