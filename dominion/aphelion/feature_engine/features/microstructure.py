from __future__ import annotations

import math
from collections import deque
from typing import Any, Sequence

from ..events import TickEvent
from ..utils import clamp, correlation, log_return, mean, normalized_entropy, safe_div, sign
from .base import FeatureContext, TickFeature


def compute_spread(bid: float, ask: float) -> float:
    return max(ask - bid, 0.0)


def compute_spread_velocity(current_spread: float, previous_spread: float, dt_ns: int) -> float:
    return safe_div(current_spread - previous_spread, max(dt_ns, 1) / 1_000_000_000)


def compute_micro_price_divergence(
    bid: float,
    ask: float,
    bid_size: float | None,
    ask_size: float | None,
    last: float,
) -> float:
    if not bid_size or not ask_size:
        mid = (bid + ask) / 2.0
        return safe_div(last - mid, mid)
    micro_price = safe_div((ask * bid_size) + (bid * ask_size), bid_size + ask_size, default=(bid + ask) / 2.0)
    mid = (bid + ask) / 2.0
    return safe_div(micro_price - mid, mid)


def compute_ofi(
    prev_bid: float | None,
    prev_ask: float | None,
    prev_bid_size: float | None,
    prev_ask_size: float | None,
    bid: float,
    ask: float,
    bid_size: float | None,
    ask_size: float | None,
) -> float:
    if prev_bid is None or prev_ask is None:
        return 0.0
    bid_size = bid_size or 0.0
    ask_size = ask_size or 0.0
    prev_bid_size = prev_bid_size or 0.0
    prev_ask_size = prev_ask_size or 0.0
    bid_pressure = bid_size if bid >= prev_bid else -prev_bid_size
    ask_pressure = -ask_size if ask <= prev_ask else prev_ask_size
    return bid_pressure + ask_pressure


def compute_tick_entropy(directions: Sequence[int]) -> float:
    return normalized_entropy(list(directions), alphabet_size=3)


def compute_hawkes_buy_sell_intensity(
    buy_intensity: float,
    sell_intensity: float,
    direction: int,
    dt_ns: int,
    decay: float,
    baseline: float,
) -> tuple[float, float]:
    dt_seconds = max(dt_ns, 1) / 1_000_000_000
    decay_multiplier = math.exp(-decay * dt_seconds)
    buy_intensity = baseline + decay_multiplier * buy_intensity + (1.0 if direction > 0 else 0.0)
    sell_intensity = baseline + decay_multiplier * sell_intensity + (1.0 if direction < 0 else 0.0)
    return buy_intensity, sell_intensity


def compute_kyles_lambda(price_changes: Sequence[float], signed_volumes: Sequence[float]) -> float:
    if len(price_changes) < 2 or len(price_changes) != len(signed_volumes):
        return 0.0
    q_var = sum(volume * volume for volume in signed_volumes) / len(signed_volumes)
    if q_var == 0:
        return 0.0
    numerator = sum(price * volume for price, volume in zip(price_changes, signed_volumes)) / len(price_changes)
    return numerator / q_var


def compute_amihud_illiquidity(abs_returns: Sequence[float], volumes: Sequence[float]) -> float:
    values = [safe_div(abs(ret), max(volume, 1e-9)) for ret, volume in zip(abs_returns, volumes)]
    return mean(values)


def compute_roll_spread(price_changes: Sequence[float]) -> float:
    if len(price_changes) < 3:
        return 0.0
    cov = sum(a * b for a, b in zip(price_changes[:-1], price_changes[1:])) / (len(price_changes) - 1)
    return 2.0 * math.sqrt(max(-cov, 0.0))


def compute_tsrv(fast_returns: Sequence[float], slow_returns: Sequence[float], slow_stride: int) -> float:
    fast_rv = sum(ret * ret for ret in fast_returns)
    slow_rv = sum(ret * ret for ret in slow_returns)
    if fast_rv == 0.0:
        return 0.0
    correction = safe_div(len(slow_returns), max(len(fast_returns), 1)) * fast_rv / max(slow_stride, 1)
    return max(slow_rv - correction, 0.0)


def compute_vpin(bucket_imbalances: Sequence[tuple[float, float]]) -> float:
    if not bucket_imbalances:
        return 0.0
    ratios = [safe_div(abs(buy - sell), max(total, 1e-9)) for buy, sell, total in bucket_imbalances]
    return mean(ratios)


def compute_toxicity_index(
    *,
    vpin: float,
    ofi: float,
    entropy: float,
    spread: float,
    spread_velocity: float,
    kyles_lambda: float,
    amihud: float,
    hawkes_imbalance: float,
) -> float:
    directional_component = clamp(abs(ofi) / 100.0, 0.0, 1.0)
    liquidity_component = clamp((spread * 10.0) + abs(spread_velocity) * 0.1, 0.0, 1.0)
    impact_component = clamp(abs(kyles_lambda) * 1_000.0 + amihud * 10_000.0, 0.0, 1.0)
    excitation_component = clamp(abs(hawkes_imbalance) / 10.0, 0.0, 1.0)
    information_component = clamp(1.0 - entropy, 0.0, 1.0)
    return clamp(
        0.28 * vpin
        + 0.18 * directional_component
        + 0.16 * liquidity_component
        + 0.16 * impact_component
        + 0.12 * excitation_component
        + 0.10 * information_component,
        0.0,
        1.0,
    )


class MicrostructureFeature(TickFeature):
    def __init__(
        self,
        *,
        name: str = "microstructure",
        version: str = "1.0.0",
        window: int = 64,
        bucket_volume: float = 500.0,
        tsrv_stride: int = 4,
        hawkes_decay: float = 1.5,
        baseline_intensity: float = 0.1,
        default_timeframe: str = "1m",
    ) -> None:
        super().__init__(name=name, version=version, default_timeframe=default_timeframe, warmup_periods=window)
        self.window = window
        self.bucket_volume = bucket_volume
        self.tsrv_stride = tsrv_stride
        self.hawkes_decay = hawkes_decay
        self.baseline_intensity = baseline_intensity

    def initialize_state(self) -> dict[str, Any]:
        return {
            "tick_count": 0,
            "last_mid": None,
            "last_last": None,
            "last_ts_event_ns": None,
            "last_spread": 0.0,
            "last_bid": None,
            "last_ask": None,
            "last_bid_size": None,
            "last_ask_size": None,
            "ofi_window": deque(maxlen=self.window),
            "directions": deque(maxlen=self.window),
            "price_changes": deque(maxlen=self.window),
            "fast_returns": deque(maxlen=self.window),
            "slow_returns": deque(maxlen=max(self.window // self.tsrv_stride, 2)),
            "signed_volumes": deque(maxlen=self.window),
            "abs_returns": deque(maxlen=self.window),
            "volumes": deque(maxlen=self.window),
            "hawkes_buy": 0.0,
            "hawkes_sell": 0.0,
            "bucket_buy": 0.0,
            "bucket_sell": 0.0,
            "bucket_volume": 0.0,
            "bucket_imbalances": deque(maxlen=self.window),
            "sample_index": 0,
            "values": {},
        }

    def update(self, event: TickEvent, state: dict[str, Any], context: FeatureContext) -> None:
        if not isinstance(event, TickEvent):
            return
        state["tick_count"] += 1
        state["sample_index"] += 1

        mid = (event.bid + event.ask) / 2.0
        spread = compute_spread(event.bid, event.ask)
        previous_mid = state["last_mid"]
        previous_last = state["last_last"]
        previous_ts = state["last_ts_event_ns"]
        dt_ns = 1 if previous_ts is None else max(event.ts_event_ns - previous_ts, 1)
        price_move = 0.0 if previous_mid is None else mid - previous_mid
        direction = sign(price_move if price_move != 0.0 else event.last - (previous_last or event.last))

        ofi = compute_ofi(
            state["last_bid"],
            state["last_ask"],
            state["last_bid_size"],
            state["last_ask_size"],
            event.bid,
            event.ask,
            event.bid_size,
            event.ask_size,
        )
        state["ofi_window"].append(ofi)
        state["directions"].append(direction)
        state["signed_volumes"].append(direction * event.volume)

        micro_divergence = compute_micro_price_divergence(
            event.bid,
            event.ask,
            event.bid_size,
            event.ask_size,
            event.last,
        )
        spread_velocity = compute_spread_velocity(spread, state["last_spread"], dt_ns)

        if previous_mid is not None and previous_mid > 0:
            ret = log_return(mid, previous_mid)
            state["fast_returns"].append(ret)
            state["price_changes"].append(price_move)
            state["abs_returns"].append(abs(ret))
            state["volumes"].append(event.volume)
            if state["sample_index"] % self.tsrv_stride == 0:
                state["slow_returns"].append(ret)
        else:
            state["price_changes"].append(0.0)

        state["hawkes_buy"], state["hawkes_sell"] = compute_hawkes_buy_sell_intensity(
            state["hawkes_buy"],
            state["hawkes_sell"],
            direction,
            dt_ns,
            self.hawkes_decay,
            self.baseline_intensity,
        )

        remaining_volume = event.volume
        while remaining_volume > 0:
            capacity = self.bucket_volume - state["bucket_volume"]
            consumed = min(capacity, remaining_volume)
            if direction >= 0:
                state["bucket_buy"] += consumed
            else:
                state["bucket_sell"] += consumed
            state["bucket_volume"] += consumed
            remaining_volume -= consumed
            if state["bucket_volume"] >= self.bucket_volume:
                state["bucket_imbalances"].append(
                    (state["bucket_buy"], state["bucket_sell"], state["bucket_volume"])
                )
                state["bucket_buy"] = 0.0
                state["bucket_sell"] = 0.0
                state["bucket_volume"] = 0.0

        ofi_value = sum(state["ofi_window"])
        entropy = compute_tick_entropy(state["directions"])
        buy_intensity = state["hawkes_buy"]
        sell_intensity = state["hawkes_sell"]
        hawkes_imbalance = safe_div(buy_intensity - sell_intensity, buy_intensity + sell_intensity)
        kyles_lambda = compute_kyles_lambda(list(state["price_changes"]), list(state["signed_volumes"]))
        amihud = compute_amihud_illiquidity(list(state["abs_returns"]), list(state["volumes"]))
        roll_spread = compute_roll_spread(list(state["price_changes"]))
        tsrv = compute_tsrv(list(state["fast_returns"]), list(state["slow_returns"]), self.tsrv_stride)
        vpin = compute_vpin(list(state["bucket_imbalances"]))

        toxicity = compute_toxicity_index(
            vpin=vpin,
            ofi=ofi_value,
            entropy=entropy,
            spread=spread,
            spread_velocity=spread_velocity,
            kyles_lambda=kyles_lambda,
            amihud=amihud,
            hawkes_imbalance=hawkes_imbalance,
        )
        state["values"] = {
            "spread": spread,
            "spread_velocity": spread_velocity,
            "micro_price_divergence": micro_divergence,
            "ofi": ofi_value,
            "vpin": vpin,
            "tick_entropy": entropy,
            "hawkes_buy_intensity": buy_intensity,
            "hawkes_sell_intensity": sell_intensity,
            "kyles_lambda": kyles_lambda,
            "amihud_illiquidity": amihud,
            "roll_spread": roll_spread,
            "tsrv": tsrv,
            "toxicity_index": toxicity,
        }

        state["last_mid"] = mid
        state["last_last"] = event.last
        state["last_ts_event_ns"] = event.ts_event_ns
        state["last_spread"] = spread
        state["last_bid"] = event.bid
        state["last_ask"] = event.ask
        state["last_bid_size"] = event.bid_size
        state["last_ask_size"] = event.ask_size

    def ready(self, state: dict[str, Any]) -> bool:
        return state["tick_count"] >= self.warmup_periods and len(state["bucket_imbalances"]) > 0

    def value(self, state: dict[str, Any]) -> dict[str, Any]:
        return dict(state["values"])


from ._microstructure_impl import (  # noqa: E402
    MicrostructureFeature as _PatchedMicrostructureFeature,
    compute_amihud_illiquidity,
    compute_bounce_rate,
    compute_hawkes_buy_sell_intensity,
    compute_hawkes_imbalance,
    compute_higuchi_fractal_dimension,
    compute_kyles_lambda,
    compute_micro_price_divergence,
    compute_ofi,
    compute_ofi_zscore,
    compute_roll_spread,
    compute_spread,
    compute_spread_velocity,
    compute_tick_entropy,
    compute_toxicity_index,
    compute_tsrv,
    compute_vpin,
)

MicrostructureFeature = _PatchedMicrostructureFeature
