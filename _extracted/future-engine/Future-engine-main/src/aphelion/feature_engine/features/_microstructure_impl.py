from __future__ import annotations

import logging
import math
from collections import deque
from typing import Any, Sequence

import numpy as np

from ..events import BarCloseEvent, TickEvent
from ..state import FeatureStateKey, FeatureStateStore
from ..utils import clamp, log_return, mean, normalized_entropy, safe_div, sign, stddev
from .base import FeatureContext, TickFeature


LOGGER = logging.getLogger("aphelion.feature_engine.microstructure")


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
    mid = (bid + ask) / 2.0
    if mid <= 0:
        return 0.0
    if not bid_size or not ask_size:
        return safe_div(last - mid, mid)
    micro_price = safe_div((ask * bid_size) + (bid * ask_size), bid_size + ask_size, default=mid)
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


def compute_hawkes_imbalance(buy_intensity: float, sell_intensity: float) -> float:
    return safe_div(buy_intensity - sell_intensity, buy_intensity + sell_intensity + 1e-9)


def compute_kyles_lambda(price_changes: Sequence[float], signed_volumes: Sequence[float]) -> float:
    if len(price_changes) < 2 or len(price_changes) != len(signed_volumes):
        return 0.0
    q_var = sum(volume * volume for volume in signed_volumes) / len(signed_volumes)
    if q_var == 0:
        return 0.0
    numerator = sum(price * volume for price, volume in zip(price_changes, signed_volumes)) / len(price_changes)
    return numerator / q_var


def compute_amihud_illiquidity(abs_returns: Sequence[float], volumes: Sequence[float]) -> float:
    return mean([safe_div(abs(ret), max(volume, 1e-9)) for ret, volume in zip(abs_returns, volumes)])


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


def compute_vpin(bucket_imbalances: Sequence[tuple[float, float, float]]) -> float:
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
    excitation_component = clamp(abs(hawkes_imbalance), 0.0, 1.0)
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


def compute_higuchi_fractal_dimension(prices: Sequence[float], k_max: int = 8) -> float | None:
    if len(prices) < 64:
        return None
    series = np.asarray(prices, dtype=float)
    n = series.shape[0]
    log_lengths: list[float] = []
    log_inverse_k: list[float] = []
    for k in range(1, k_max + 1):
        lengths: list[float] = []
        for m in range(k):
            max_i = (n - 1 - m) // k
            if max_i <= 0:
                continue
            total = 0.0
            for idx in range(1, max_i + 1):
                total += abs(series[m + idx * k] - series[m + (idx - 1) * k])
            scaled = safe_div(n - 1, max_i * (k * k), default=0.0) * total
            if scaled > 0.0:
                lengths.append(scaled)
        if lengths:
            avg_length = mean(lengths)
            if avg_length > 0.0:
                log_lengths.append(math.log(avg_length))
                log_inverse_k.append(math.log(1.0 / k))
    if len(log_lengths) < 2:
        return None
    slope, _ = np.polyfit(log_inverse_k, log_lengths, 1)
    return clamp(float(slope), 1.0, 2.0)


def compute_bounce_rate(directions: Sequence[int]) -> float:
    if len(directions) < 64:
        return 0.0
    sign_changes = 0
    for prev_direction, next_direction in zip(directions[:-1], directions[1:]):
        if prev_direction == 0 or next_direction == 0:
            continue
        if prev_direction != next_direction:
            sign_changes += 1
    return sign_changes / 63.0


def compute_ofi_zscore(ofi_raw: float, samples: Sequence[float], warmup: int) -> float:
    if len(samples) < warmup:
        return 0.0
    return safe_div(ofi_raw - mean(samples), stddev(samples) + 1e-9)


ALIAS_MAP = {
    "spread": "ms_spread",
    "spread_velocity": "ms_spread_velocity",
    "micro_price_divergence": "ms_micro_price_divergence",
    "ofi_raw": "ms_ofi_raw",
    "ofi": "ms_ofi",
    "ofi_zscore_100": "ms_ofi_zscore_100",
    "ofi_zscore_500": "ms_ofi_zscore_500",
    "ofi_normalized": "ms_ofi_normalized",
    "vpin": "ms_vpin",
    "vpin_bucket_volume": "ms_vpin_bucket_volume",
    "vpin_buckets_completed": "ms_vpin_buckets_completed",
    "tick_entropy": "ms_tick_entropy",
    "hawkes_buy_intensity": "ms_hawkes_buy_intensity",
    "hawkes_sell_intensity": "ms_hawkes_sell_intensity",
    "hawkes_imbalance": "ms_hawkes_imbalance",
    "kyles_lambda": "ms_kyles_lambda",
    "amihud_illiquidity": "ms_amihud_illiquidity",
    "roll_spread": "ms_roll_spread",
    "tsrv": "ms_tsrv",
    "toxicity": "ms_toxicity",
    "toxicity_index": "ms_toxicity",
    "implied_vol": "ms_implied_vol",
    "vrp": "ms_vrp",
    "fractal_dimension": "ms_fractal_dimension",
    "tick_run_length": "ms_tick_run_length",
    "tick_run_direction": "ms_tick_run_direction",
    "bounce_rate_64": "ms_bounce_rate_64",
    "tick_rate_current": "ms_tick_rate_current",
    "quote_stuffing_flag": "ms_quote_stuffing_flag",
}


class MicrostructureFeature(TickFeature):
    event_types = (TickEvent, BarCloseEvent)

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
        self._seed_volumes: deque[float] = deque(maxlen=500)
        self._seed_bucket_volume = bucket_volume
        self._standalone_store = FeatureStateStore()
        self._standalone_state = self.initialize_state()
        self._standalone_realized_vol_gk: float | None = None

    def calibrate(self, ticks: list[TickEvent]) -> None:
        for tick in ticks[-500:]:
            self._seed_volumes.append(max(tick.volume, 0.0))
        if self._seed_volumes:
            self._seed_bucket_volume = max(float(np.percentile(list(self._seed_volumes), 50)), 1e-9)
        self._standalone_state["volume_calibration_window"] = deque(self._seed_volumes, maxlen=500)
        self._standalone_state["current_bucket_volume_target"] = self._seed_bucket_volume
        self._refresh_values(self._standalone_state)

    def set_realized_volatility(self, realized_vol_gk: float | None) -> None:
        self._standalone_realized_vol_gk = realized_vol_gk
        self._standalone_state["external_realized_vol_gk"] = realized_vol_gk
        self._refresh_values(self._standalone_state)

    def on_tick(self, event: TickEvent) -> None:
        self._standalone_store.update_tick(event)
        context = FeatureContext(
            state_store=self._standalone_store,
            primary_symbol=event.symbol,
            event=event,
            default_timeframe=self.default_timeframe,
        )
        self.update(event, self._standalone_state, context)

    def on_bar(self, event: BarCloseEvent) -> None:
        self._standalone_store.update_bar(event)
        context = FeatureContext(
            state_store=self._standalone_store,
            primary_symbol=event.symbol,
            event=event,
            default_timeframe=event.timeframe,
        )
        self.update(event, self._standalone_state, context)

    def warmup_complete(self) -> bool:
        return self.ready(self._standalone_state)

    def initialize_state(self) -> dict[str, Any]:
        state = {
            "tick_count": 0,
            "bar_count": 0,
            "last_mid": None,
            "last_last": None,
            "last_ts_event_ns": None,
            "last_spread": 0.0,
            "last_spread_velocity": 0.0,
            "last_bid": None,
            "last_ask": None,
            "last_bid_size": None,
            "last_ask_size": None,
            "ofi_window": deque(maxlen=self.window),
            "ofi_raw_window_100": deque(maxlen=100),
            "ofi_raw_window_500": deque(maxlen=500),
            "directions": deque(maxlen=self.window),
            "bounce_directions": deque(maxlen=64),
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
            "bucket_volume_progress": 0.0,
            "current_bucket_volume_target": self._seed_bucket_volume,
            "bucket_imbalances": deque(maxlen=self.window),
            "sample_index": 0,
            "vpin_buckets_completed": 0,
            "volume_calibration_window": deque(self._seed_volumes, maxlen=500),
            "ticks_since_calibration": 0,
            "last_implied_vol": None,
            "fractal_closes": deque(maxlen=64),
            "tick_run_length": 0,
            "tick_run_direction": 0,
            "neutral_pause": False,
            "quote_current_second": None,
            "quote_current_count": 0,
            "quote_recent_seconds": deque(maxlen=10),
            "quote_rate_history": deque(maxlen=1000),
            "external_realized_vol_gk": None,
            "values": {},
        }
        state["values"] = self._default_values(state)
        return state

    def update(self, event: TickEvent | BarCloseEvent, state: dict[str, Any], context: FeatureContext) -> None:
        if isinstance(event, TickEvent):
            self._update_tick(event, state, context)
        elif isinstance(event, BarCloseEvent) and event.timeframe == self.default_timeframe:
            state["bar_count"] += 1
            state["fractal_closes"].append(event.close)
            self._refresh_values(state, context=context)

    def _update_tick(self, event: TickEvent, state: dict[str, Any], context: FeatureContext) -> None:
        previous_ts = state["last_ts_event_ns"]
        if previous_ts is not None and event.ts_event_ns < previous_ts:
            LOGGER.warning(
                "Skipping out-of-order tick symbol=%s event_ts_ns=%s previous_ts_ns=%s",
                event.symbol,
                event.ts_event_ns,
                previous_ts,
            )
            return

        state["tick_count"] += 1
        state["sample_index"] += 1
        state["ticks_since_calibration"] += 1
        state["volume_calibration_window"].append(max(event.volume, 0.0))
        if event.implied_vol is not None:
            state["last_implied_vol"] = event.implied_vol
        if state["ticks_since_calibration"] >= 50 and state["volume_calibration_window"]:
            state["current_bucket_volume_target"] = max(
                float(np.percentile(list(state["volume_calibration_window"]), 50)),
                1e-9,
            )
            state["ticks_since_calibration"] = 0

        self._update_quote_stuffing(event, state)

        previous_last = state["last_last"]
        spread = compute_spread(event.bid, event.ask)
        dt_ns = 1 if previous_ts is None else max(event.ts_event_ns - previous_ts, 1)
        last_price_change = 0.0 if previous_last is None else event.last - previous_last
        direction = sign(last_price_change)
        spread_velocity = compute_spread_velocity(spread, state["last_spread"], dt_ns)
        state["last_spread_velocity"] = spread_velocity

        ofi_raw = compute_ofi(
            state["last_bid"],
            state["last_ask"],
            state["last_bid_size"],
            state["last_ask_size"],
            event.bid,
            event.ask,
            event.bid_size,
            event.ask_size,
        )
        state["ofi_window"].append(ofi_raw)
        state["ofi_raw_window_100"].append(ofi_raw)
        state["ofi_raw_window_500"].append(ofi_raw)
        state["directions"].append(direction)
        state["bounce_directions"].append(direction)
        state["signed_volumes"].append(direction * max(event.volume, 0.0))

        if previous_last is not None and previous_last > 0.0:
            tick_return = log_return(event.last, previous_last)
            state["fast_returns"].append(tick_return)
            state["price_changes"].append(last_price_change)
            state["abs_returns"].append(abs(tick_return))
            state["volumes"].append(max(event.volume, 0.0))
            if state["sample_index"] % self.tsrv_stride == 0:
                state["slow_returns"].append(tick_return)
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
        self._update_tick_run(direction, state)
        self._consume_vpin_volume(state, max(event.volume, 0.0), direction)

        state["last_mid"] = (event.bid + event.ask) / 2.0
        state["last_last"] = event.last
        state["last_ts_event_ns"] = event.ts_event_ns
        state["last_spread"] = spread
        state["last_bid"] = event.bid
        state["last_ask"] = event.ask
        state["last_bid_size"] = event.bid_size
        state["last_ask_size"] = event.ask_size
        self._refresh_values(state, context=context)

    def _update_tick_run(self, direction: int, state: dict[str, Any]) -> None:
        if state["tick_run_length"] == 0:
            state["tick_run_length"] = 1
            if direction != 0:
                state["tick_run_direction"] = direction
            return
        if direction == 0:
            state["neutral_pause"] = True
            return
        if state["tick_run_direction"] == 0:
            state["tick_run_direction"] = direction
            state["neutral_pause"] = False
            return
        if direction == state["tick_run_direction"]:
            if state["neutral_pause"]:
                state["neutral_pause"] = False
                return
            state["tick_run_length"] += 1
            return
        state["tick_run_direction"] = direction
        state["tick_run_length"] = 1
        state["neutral_pause"] = False

    def _update_quote_stuffing(self, event: TickEvent, state: dict[str, Any]) -> None:
        event_second = event.ts_event_ns // 1_000_000_000
        current_second = state["quote_current_second"]
        if current_second is None:
            state["quote_current_second"] = event_second
            state["quote_current_count"] = 1
            return
        if event_second == current_second:
            state["quote_current_count"] += 1
            return
        if event_second < current_second:
            return
        self._finalize_quote_second(state, current_second, state["quote_current_count"])
        for missing_second in range(current_second + 1, event_second):
            self._finalize_quote_second(state, missing_second, 0)
        state["quote_current_second"] = event_second
        state["quote_current_count"] = 1

    def _finalize_quote_second(self, state: dict[str, Any], second: int, count: int) -> None:
        state["quote_recent_seconds"].append((second, count))
        state["quote_rate_history"].append(count)

    def _consume_vpin_volume(self, state: dict[str, Any], volume: float, direction: int) -> None:
        remaining_volume = max(volume, 0.0)
        target = max(state["current_bucket_volume_target"], 1e-9)
        while state["bucket_volume_progress"] >= target and target > 0.0:
            self._finalize_vpin_bucket(state, target)
            target = max(state["current_bucket_volume_target"], 1e-9)
        while remaining_volume > 0.0:
            target = max(state["current_bucket_volume_target"], 1e-9)
            capacity = max(target - state["bucket_volume_progress"], 0.0)
            if capacity == 0.0:
                self._finalize_vpin_bucket(state, target)
                continue
            consumed = min(capacity, remaining_volume)
            if direction > 0:
                state["bucket_buy"] += consumed
            elif direction < 0:
                state["bucket_sell"] += consumed
            else:
                state["bucket_buy"] += consumed * 0.5
                state["bucket_sell"] += consumed * 0.5
            state["bucket_volume_progress"] += consumed
            remaining_volume -= consumed
            if state["bucket_volume_progress"] + 1e-12 >= target:
                self._finalize_vpin_bucket(state, target)

    def _finalize_vpin_bucket(self, state: dict[str, Any], target_volume: float) -> None:
        current_volume = state["bucket_volume_progress"]
        if current_volume <= 0.0:
            return
        emitted_volume = min(current_volume, target_volume)
        buy_ratio = safe_div(state["bucket_buy"], current_volume, default=0.5)
        sell_ratio = safe_div(state["bucket_sell"], current_volume, default=0.5)
        emitted_buy = emitted_volume * buy_ratio
        emitted_sell = emitted_volume * sell_ratio
        state["bucket_imbalances"].append((emitted_buy, emitted_sell, emitted_volume))
        state["vpin_buckets_completed"] += 1
        state["bucket_buy"] = max(state["bucket_buy"] - emitted_buy, 0.0)
        state["bucket_sell"] = max(state["bucket_sell"] - emitted_sell, 0.0)
        state["bucket_volume_progress"] = max(current_volume - emitted_volume, 0.0)

    def _resolve_realized_vol_gk(self, state: dict[str, Any], context: FeatureContext | None) -> float | None:
        if state.get("external_realized_vol_gk") is not None:
            return state["external_realized_vol_gk"]
        if context is None:
            return self._standalone_realized_vol_gk
        symbol = getattr(context.event, "symbol", context.primary_symbol)
        timeframe = getattr(context.event, "timeframe", self.default_timeframe)
        technical_state = context.state_store.feature_states.get(FeatureStateKey("technical", symbol, timeframe))
        if technical_state is None:
            technical_state = context.state_store.feature_states.get(
                FeatureStateKey("technical", symbol, self.default_timeframe)
            )
        if technical_state is None:
            return self._standalone_realized_vol_gk
        return technical_state.get("values", {}).get("realized_vol_gk")

    def _default_values(self, state: dict[str, Any]) -> dict[str, Any]:
        values = {
            "ms_spread": 0.0,
            "ms_spread_velocity": state.get("last_spread_velocity", 0.0),
            "ms_micro_price_divergence": 0.0,
            "ms_ofi_raw": 0.0,
            "ms_ofi": 0.0,
            "ms_ofi_zscore_100": 0.0,
            "ms_ofi_zscore_500": 0.0,
            "ms_ofi_normalized": 0.0,
            "ms_vpin": 0.0,
            "ms_vpin_bucket_volume": state.get("current_bucket_volume_target", self._seed_bucket_volume),
            "ms_vpin_buckets_completed": state.get("vpin_buckets_completed", 0),
            "ms_tick_entropy": 0.0,
            "ms_hawkes_buy_intensity": 0.0,
            "ms_hawkes_sell_intensity": 0.0,
            "ms_hawkes_imbalance": 0.0,
            "ms_kyles_lambda": 0.0,
            "ms_amihud_illiquidity": 0.0,
            "ms_roll_spread": 0.0,
            "ms_tsrv": 0.0,
            "ms_toxicity": 0.0,
            "ms_implied_vol": state.get("last_implied_vol"),
            "ms_vrp": None,
            "ms_fractal_dimension": None,
            "ms_tick_run_length": state.get("tick_run_length", 0),
            "ms_tick_run_direction": state.get("tick_run_direction", 0),
            "ms_bounce_rate_64": 0.0,
            "ms_tick_rate_current": state.get("quote_current_count", 0),
            "ms_quote_stuffing_flag": False,
        }
        for alias_name, ms_name in ALIAS_MAP.items():
            values[alias_name] = values[ms_name]
        return values

    def _refresh_values(self, state: dict[str, Any], context: FeatureContext | None = None) -> None:
        values = self._default_values(state)
        spread = state["last_spread"]
        ofi_raw = state["ofi_window"][-1] if state["ofi_window"] else 0.0
        ofi_value = sum(state["ofi_window"])
        entropy = compute_tick_entropy(list(state["directions"]))
        buy_intensity = state["hawkes_buy"]
        sell_intensity = state["hawkes_sell"]
        hawkes_imbalance = compute_hawkes_imbalance(buy_intensity, sell_intensity)
        kyles_lambda = compute_kyles_lambda(list(state["price_changes"]), list(state["signed_volumes"]))
        amihud = compute_amihud_illiquidity(list(state["abs_returns"]), list(state["volumes"]))
        roll_spread = compute_roll_spread(list(state["price_changes"]))
        tsrv = compute_tsrv(list(state["fast_returns"]), list(state["slow_returns"]), self.tsrv_stride)
        vpin = compute_vpin(list(state["bucket_imbalances"]))
        quote_history = list(state["quote_rate_history"])
        quote_threshold = float(np.percentile(quote_history, 99)) if len(quote_history) >= 100 else math.inf
        implied_vol = state["last_implied_vol"]
        realized_vol_gk = self._resolve_realized_vol_gk(state, context)
        if state["last_bid"] is not None and state["last_ask"] is not None and state["last_last"] is not None:
            micro_divergence = compute_micro_price_divergence(
                state["last_bid"],
                state["last_ask"],
                state["last_bid_size"],
                state["last_ask_size"],
                state["last_last"],
            )
        else:
            micro_divergence = 0.0
        values.update(
            {
                "ms_spread": spread,
                "ms_spread_velocity": state["last_spread_velocity"],
                "ms_micro_price_divergence": micro_divergence,
                "ms_ofi_raw": ofi_raw,
                "ms_ofi": ofi_value,
                "ms_ofi_zscore_100": compute_ofi_zscore(ofi_raw, list(state["ofi_raw_window_100"]), 100),
                "ms_ofi_zscore_500": compute_ofi_zscore(ofi_raw, list(state["ofi_raw_window_500"]), 500),
                "ms_vpin": vpin,
                "ms_vpin_bucket_volume": state["current_bucket_volume_target"],
                "ms_vpin_buckets_completed": state["vpin_buckets_completed"],
                "ms_tick_entropy": entropy,
                "ms_hawkes_buy_intensity": buy_intensity,
                "ms_hawkes_sell_intensity": sell_intensity,
                "ms_hawkes_imbalance": hawkes_imbalance,
                "ms_kyles_lambda": kyles_lambda,
                "ms_amihud_illiquidity": amihud,
                "ms_roll_spread": roll_spread,
                "ms_tsrv": tsrv,
                "ms_toxicity": compute_toxicity_index(
                    vpin=vpin,
                    ofi=ofi_value,
                    entropy=entropy,
                    spread=spread,
                    spread_velocity=state["last_spread_velocity"],
                    kyles_lambda=kyles_lambda,
                    amihud=amihud,
                    hawkes_imbalance=hawkes_imbalance,
                ),
                "ms_implied_vol": implied_vol,
                "ms_vrp": None if implied_vol is None or realized_vol_gk is None else implied_vol - realized_vol_gk,
                "ms_fractal_dimension": compute_higuchi_fractal_dimension(list(state["fractal_closes"])),
                "ms_tick_run_length": state["tick_run_length"],
                "ms_tick_run_direction": state["tick_run_direction"],
                "ms_bounce_rate_64": compute_bounce_rate(list(state["bounce_directions"])),
                "ms_tick_rate_current": state["quote_current_count"],
                "ms_quote_stuffing_flag": len(quote_history) >= 100 and state["quote_current_count"] > quote_threshold,
            }
        )
        values["ms_ofi_normalized"] = values["ms_ofi_zscore_100"]
        for alias_name, ms_name in ALIAS_MAP.items():
            values[alias_name] = values[ms_name]
        state["values"] = values

    def ready(self, state: dict[str, Any]) -> bool:
        return state["tick_count"] >= self.warmup_periods

    def value(self, state: dict[str, Any] | None = None) -> dict[str, Any]:
        return dict((self._standalone_state if state is None else state)["values"])
