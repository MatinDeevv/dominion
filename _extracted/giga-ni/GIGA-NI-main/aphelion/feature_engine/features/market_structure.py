from __future__ import annotations

from collections import deque
from typing import Any, Sequence

from ..events import BarCloseEvent
from ..utils import mean, safe_div
from .base import BarFeature, FeatureContext


def _bar_to_dict(event: BarCloseEvent) -> dict[str, float | int]:
    return {
        "ts_event_ns": event.ts_event_ns,
        "open": event.open,
        "high": event.high,
        "low": event.low,
        "close": event.close,
        "volume": event.volume,
    }


def detect_swing_highs_lows(bars: Sequence[dict[str, float | int]], lookback: int) -> dict[str, Any] | None:
    if len(bars) < (2 * lookback) + 1:
        return None
    center_index = len(bars) - lookback - 1
    center_bar = bars[center_index]
    left = bars[center_index - lookback : center_index]
    right = bars[center_index + 1 : center_index + 1 + lookback]
    is_swing_high = all(center_bar["high"] > item["high"] for item in left + right)
    is_swing_low = all(center_bar["low"] < item["low"] for item in left + right)
    if is_swing_high:
        return {"kind": "high", "price": center_bar["high"], "ts_event_ns": center_bar["ts_event_ns"]}
    if is_swing_low:
        return {"kind": "low", "price": center_bar["low"], "ts_event_ns": center_bar["ts_event_ns"]}
    return None


def detect_fair_value_gaps(bars: Sequence[dict[str, float | int]]) -> list[dict[str, Any]]:
    if len(bars) < 3:
        return []
    a, b, c = bars[-3], bars[-2], bars[-1]
    gaps: list[dict[str, Any]] = []
    if c["low"] > a["high"]:
        gaps.append({"side": "bullish", "low": a["high"], "high": c["low"], "created_ts": c["ts_event_ns"]})
    if c["high"] < a["low"]:
        gaps.append({"side": "bearish", "low": c["high"], "high": a["low"], "created_ts": c["ts_event_ns"]})
    return gaps


def detect_bos(close_price: float, last_swing_high: float | None, last_swing_low: float | None) -> dict[str, bool]:
    return {
        "bullish_bos": bool(last_swing_high is not None and close_price > last_swing_high),
        "bearish_bos": bool(last_swing_low is not None and close_price < last_swing_low),
    }


def detect_choch(prior_trend: str, bos: dict[str, bool]) -> dict[str, bool]:
    return {
        "bullish_choch": prior_trend == "down" and bos["bullish_bos"],
        "bearish_choch": prior_trend == "up" and bos["bearish_bos"],
    }


def detect_order_blocks(
    bars: Sequence[dict[str, float | int]],
    bos: dict[str, bool],
) -> list[dict[str, Any]]:
    if len(bars) < 2:
        return []
    previous = bars[-2]
    blocks: list[dict[str, Any]] = []
    if bos["bullish_bos"] and previous["close"] < previous["open"]:
        blocks.append({"side": "bullish", "low": previous["low"], "high": previous["open"], "active": True})
    if bos["bearish_bos"] and previous["close"] > previous["open"]:
        blocks.append({"side": "bearish", "low": previous["open"], "high": previous["high"], "active": True})
    return blocks


def detect_liquidity_pools(swings: Sequence[dict[str, Any]], tolerance: float = 0.0005) -> list[dict[str, Any]]:
    pools: list[dict[str, Any]] = []
    highs = [swing for swing in swings if swing["kind"] == "high"]
    lows = [swing for swing in swings if swing["kind"] == "low"]
    for cohort, side in ((highs, "sell_side"), (lows, "buy_side")):
        if len(cohort) < 2:
            continue
        last_two = cohort[-2:]
        anchor = mean([item["price"] for item in last_two])
        if all(abs(item["price"] - anchor) <= anchor * tolerance for item in last_two):
            pools.append({"side": side, "price": anchor, "touches": len(last_two)})
    return pools


def detect_breaker_blocks(order_blocks: Sequence[dict[str, Any]], close_price: float) -> list[dict[str, Any]]:
    breakers: list[dict[str, Any]] = []
    for block in order_blocks:
        if block["side"] == "bearish" and close_price > block["high"]:
            breakers.append({"side": "bullish_breaker", "low": block["low"], "high": block["high"]})
        elif block["side"] == "bullish" and close_price < block["low"]:
            breakers.append({"side": "bearish_breaker", "low": block["low"], "high": block["high"]})
    return breakers


def detect_volume_imbalances(
    bar: dict[str, float | int],
    average_volume: float,
    average_range: float,
) -> dict[str, float | bool]:
    body = abs(bar["close"] - bar["open"])
    price_range = max(bar["high"] - bar["low"], 1e-9)
    displacement = body / price_range
    high_volume = bar["volume"] > average_volume * 1.5 if average_volume > 0 else False
    compressed = price_range > average_range if average_range > 0 else True
    return {
        "bullish_volume_imbalance": bool(high_volume and compressed and bar["close"] > bar["open"] and displacement > 0.7),
        "bearish_volume_imbalance": bool(high_volume and compressed and bar["close"] < bar["open"] and displacement > 0.7),
        "imbalance_score": displacement * safe_div(bar["volume"], average_volume, default=0.0),
    }


class MarketStructureFeature(BarFeature):
    def __init__(
        self,
        *,
        name: str = "market_structure",
        version: str = "1.0.0",
        lookback: int = 2,
        history: int = 128,
        default_timeframe: str = "15m",
    ) -> None:
        super().__init__(name=name, version=version, default_timeframe=default_timeframe, warmup_periods=(2 * lookback) + 1)
        self.lookback = lookback
        self.history = history

    def initialize_state(self) -> dict[str, Any]:
        return {
            "bars": deque(maxlen=self.history),
            "swings": deque(maxlen=self.history),
            "active_fvgs": deque(maxlen=32),
            "order_blocks": deque(maxlen=32),
            "breaker_blocks": deque(maxlen=32),
            "trend": "neutral",
            "values": {},
        }

    def update(self, event: BarCloseEvent, state: dict[str, Any], context: FeatureContext) -> None:
        if not isinstance(event, BarCloseEvent):
            return

        bar = _bar_to_dict(event)
        state["bars"].append(bar)
        bars = list(state["bars"])

        swing = detect_swing_highs_lows(bars, self.lookback)
        if swing is not None and (not state["swings"] or state["swings"][-1]["ts_event_ns"] != swing["ts_event_ns"]):
            state["swings"].append(swing)

        swings = list(state["swings"])
        last_swing_high = next((item["price"] for item in reversed(swings) if item["kind"] == "high"), None)
        last_swing_low = next((item["price"] for item in reversed(swings) if item["kind"] == "low"), None)
        bos = detect_bos(event.close, last_swing_high, last_swing_low)
        choch = detect_choch(state["trend"], bos)
        if bos["bullish_bos"]:
            state["trend"] = "up"
        elif bos["bearish_bos"]:
            state["trend"] = "down"

        for gap in detect_fair_value_gaps(bars):
            state["active_fvgs"].append(gap)

        active_fvgs = deque(
            [
                gap
                for gap in state["active_fvgs"]
                if not (gap["side"] == "bullish" and event.low <= gap["low"])
                and not (gap["side"] == "bearish" and event.high >= gap["high"])
            ],
            maxlen=32,
        )
        state["active_fvgs"] = active_fvgs

        for block in detect_order_blocks(bars, bos):
            state["order_blocks"].append(block)
        for breaker in detect_breaker_blocks(list(state["order_blocks"]), event.close):
            state["breaker_blocks"].append(breaker)

        recent_ranges = [item["high"] - item["low"] for item in bars[-20:]]
        average_range = mean(recent_ranges)
        average_volume = mean([item["volume"] for item in bars[-20:]])
        volume_imbalance = detect_volume_imbalances(bar, average_volume, average_range)
        pools = detect_liquidity_pools(swings)

        nearest_bullish_ob = next((block for block in reversed(state["order_blocks"]) if block["side"] == "bullish"), None)
        nearest_bearish_ob = next((block for block in reversed(state["order_blocks"]) if block["side"] == "bearish"), None)
        nearest_bullish_fvg = next((gap for gap in reversed(state["active_fvgs"]) if gap["side"] == "bullish"), None)
        nearest_bearish_fvg = next((gap for gap in reversed(state["active_fvgs"]) if gap["side"] == "bearish"), None)

        state["values"] = {
            "last_swing_high": last_swing_high,
            "last_swing_low": last_swing_low,
            "liquidity_pool_buy_side": next((pool["price"] for pool in pools if pool["side"] == "buy_side"), None),
            "liquidity_pool_sell_side": next((pool["price"] for pool in pools if pool["side"] == "sell_side"), None),
            "bullish_bos": bos["bullish_bos"],
            "bearish_bos": bos["bearish_bos"],
            "bullish_choch": choch["bullish_choch"],
            "bearish_choch": choch["bearish_choch"],
            "bullish_order_block_low": nearest_bullish_ob["low"] if nearest_bullish_ob else None,
            "bullish_order_block_high": nearest_bullish_ob["high"] if nearest_bullish_ob else None,
            "bearish_order_block_low": nearest_bearish_ob["low"] if nearest_bearish_ob else None,
            "bearish_order_block_high": nearest_bearish_ob["high"] if nearest_bearish_ob else None,
            "bullish_fvg_low": nearest_bullish_fvg["low"] if nearest_bullish_fvg else None,
            "bullish_fvg_high": nearest_bullish_fvg["high"] if nearest_bullish_fvg else None,
            "bearish_fvg_low": nearest_bearish_fvg["low"] if nearest_bearish_fvg else None,
            "bearish_fvg_high": nearest_bearish_fvg["high"] if nearest_bearish_fvg else None,
            "bullish_breaker_count": sum(1 for item in state["breaker_blocks"] if item["side"] == "bullish_breaker"),
            "bearish_breaker_count": sum(1 for item in state["breaker_blocks"] if item["side"] == "bearish_breaker"),
            "bullish_volume_imbalance": volume_imbalance["bullish_volume_imbalance"],
            "bearish_volume_imbalance": volume_imbalance["bearish_volume_imbalance"],
            "volume_imbalance_score": volume_imbalance["imbalance_score"],
            "trend": state["trend"],
        }

    def ready(self, state: dict[str, Any]) -> bool:
        return len(state["bars"]) >= self.warmup_periods

    def value(self, state: dict[str, Any]) -> dict[str, Any]:
        return dict(state["values"])

