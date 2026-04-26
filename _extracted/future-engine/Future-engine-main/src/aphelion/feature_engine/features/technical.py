from __future__ import annotations

import math
from collections import deque
from typing import Any, Sequence

from ..events import BarCloseEvent
from ..utils import log_return, mean, safe_div, stddev
from .base import BarFeature, FeatureContext


def compute_atr(atr_value: float | None) -> float | None:
    return atr_value


def compute_bollinger_bands(window: Sequence[float], num_std: float = 2.0) -> dict[str, float] | None:
    if len(window) < 2:
        return None
    mid = mean(window)
    sigma = stddev(list(window))
    return {"upper": mid + num_std * sigma, "mid": mid, "lower": mid - num_std * sigma}


def compute_rsi(avg_gain: float | None, avg_loss: float | None) -> float | None:
    if avg_gain is None or avg_loss is None:
        return None
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def compute_macd(fast_ema: float | None, slow_ema: float | None, signal_ema: float | None) -> dict[str, float] | None:
    if fast_ema is None or slow_ema is None or signal_ema is None:
        return None
    line = fast_ema - slow_ema
    return {"line": line, "signal": signal_ema, "histogram": line - signal_ema}


def compute_ema_ladder(ema_values: dict[int, float | None]) -> dict[str, float]:
    return {str(period): value for period, value in ema_values.items() if value is not None}


def compute_sma_ladder(close_windows: dict[int, deque[float]]) -> dict[str, float]:
    payload: dict[str, float] = {}
    for period, window in close_windows.items():
        if window:
            payload[str(period)] = mean(list(window))
    return payload


def compute_stochastic(window: Sequence[dict[str, float]], k_history: Sequence[float]) -> dict[str, float] | None:
    if not window:
        return None
    highest_high = max(bar["high"] for bar in window)
    lowest_low = min(bar["low"] for bar in window)
    last_close = window[-1]["close"]
    k = safe_div(last_close - lowest_low, max(highest_high - lowest_low, 1e-9)) * 100.0
    d = mean(list(k_history) + [k]) if k_history else k
    return {"k": k, "d": d}


def compute_adx(adx_value: float | None, plus_di: float | None, minus_di: float | None) -> dict[str, float] | None:
    if adx_value is None or plus_di is None or minus_di is None:
        return None
    return {"adx": adx_value, "plus_di": plus_di, "minus_di": minus_di}


def compute_garman_klass_term(open_price: float, high_price: float, low_price: float, close_price: float) -> float | None:
    if min(open_price, high_price, low_price, close_price) <= 0.0:
        return None
    hl_term = math.log(high_price / low_price) if high_price > 0.0 and low_price > 0.0 else 0.0
    oc_term = math.log(close_price / open_price) if open_price > 0.0 else 0.0
    return max(0.5 * (hl_term**2) - ((2.0 * math.log(2.0)) - 1.0) * (oc_term**2), 0.0)


def compute_realized_vol_gk(window: Sequence[float], period: int) -> float | None:
    if len(window) < period:
        return None
    return math.sqrt(max(mean(window), 0.0))


def compute_realized_vol_pk(log_ranges_sq: Sequence[float], period: int) -> float | None:
    if len(log_ranges_sq) < period:
        return None
    denominator = 4.0 * period * math.log(2.0)
    return math.sqrt(max(sum(log_ranges_sq) / denominator, 0.0))


def compute_realized_vol_yz(
    overnight_returns: Sequence[float],
    open_close_returns: Sequence[float],
    realized_vol_gk: float | None,
    period: int,
) -> float | None:
    if len(overnight_returns) < period or len(open_close_returns) < period or realized_vol_gk is None:
        return None
    if period <= 1:
        return None
    overnight_mean = mean(overnight_returns)
    open_close_mean = mean(open_close_returns)
    overnight_var = sum((value - overnight_mean) ** 2 for value in overnight_returns) / (period - 1)
    open_close_var = sum((value - open_close_mean) ** 2 for value in open_close_returns) / (period - 1)
    k = 0.34 / (1.34 + (period + 1) / (period - 1))
    return math.sqrt(max(overnight_var + k * open_close_var + (1.0 - k) * (realized_vol_gk**2), 0.0))


def compute_bar_tsrv(fast_returns: Sequence[float], slow_returns: Sequence[float], stride: int) -> float:
    fast_rv = sum(ret * ret for ret in fast_returns)
    slow_rv = sum(ret * ret for ret in slow_returns)
    if fast_rv == 0.0:
        return 0.0
    correction = safe_div(len(slow_returns), max(len(fast_returns), 1)) * fast_rv / max(stride, 1)
    return max(slow_rv - correction, 0.0)


class TechnicalFeature(BarFeature):
    def __init__(
        self,
        *,
        name: str = "technical",
        version: str = "1.0.0",
        atr_periods: tuple[int, ...] = (5, 10, 14, 20, 50),
        bollinger_periods: tuple[int, ...] = (10, 20, 50),
        rsi_periods: tuple[int, ...] = (7, 14, 21),
        ladder_periods: tuple[int, ...] = (5, 10, 20, 50, 100, 200),
        stochastic_periods: tuple[int, ...] = (14, 21),
        adx_period: int = 14,
        realized_vol_window: int = 20,
        tsrv_stride: int = 4,
        default_timeframe: str = "1m",
    ) -> None:
        warmup = max(
            max(atr_periods),
            max(bollinger_periods),
            max(rsi_periods),
            max(ladder_periods),
            max(stochastic_periods),
            adx_period,
            realized_vol_window + 1,
        )
        super().__init__(name=name, version=version, default_timeframe=default_timeframe, warmup_periods=warmup)
        self.atr_periods = atr_periods
        self.bollinger_periods = bollinger_periods
        self.rsi_periods = rsi_periods
        self.ladder_periods = ladder_periods
        self.ema_periods = tuple(sorted(set(ladder_periods) | {12, 26}))
        self.stochastic_periods = stochastic_periods
        self.adx_period = adx_period
        self.realized_vol_window = realized_vol_window
        self.tsrv_stride = tsrv_stride
        self._standalone_state = self.initialize_state()

    def on_bar(self, event: BarCloseEvent) -> None:
        self.update(event, self._standalone_state, FeatureContext(object(), event.symbol, event, event.timeframe))

    def warmup_complete(self) -> bool:
        return self.ready(self._standalone_state)

    def initialize_state(self) -> dict[str, Any]:
        return {
            "bar_count": 0,
            "prev_close": None,
            "prev_high": None,
            "prev_low": None,
            "atr_windows": {period: deque(maxlen=period) for period in self.atr_periods},
            "atr_values": {period: None for period in self.atr_periods},
            "gain_windows": {period: deque(maxlen=period) for period in self.rsi_periods},
            "loss_windows": {period: deque(maxlen=period) for period in self.rsi_periods},
            "avg_gain": {period: None for period in self.rsi_periods},
            "avg_loss": {period: None for period in self.rsi_periods},
            "close_windows": {period: deque(maxlen=period) for period in set(self.ladder_periods) | set(self.bollinger_periods)},
            "ema_values": {period: None for period in self.ema_periods},
            "stoch_windows": {period: deque(maxlen=period) for period in self.stochastic_periods},
            "stoch_k_history": {period: deque(maxlen=3) for period in self.stochastic_periods},
            "macd_signal": None,
            "adx": {
                "tr_seed": deque(maxlen=self.adx_period),
                "plus_seed": deque(maxlen=self.adx_period),
                "minus_seed": deque(maxlen=self.adx_period),
                "dx_seed": deque(maxlen=self.adx_period),
                "tr14": None,
                "plus_dm14": None,
                "minus_dm14": None,
                "adx": None,
                "plus_di": None,
                "minus_di": None,
            },
            "gk_terms": deque(maxlen=self.realized_vol_window),
            "overnight_returns": deque(maxlen=self.realized_vol_window),
            "open_close_returns": deque(maxlen=self.realized_vol_window),
            "pk_log_ranges_sq": deque(maxlen=self.realized_vol_window),
            "rv_fast_returns": deque(maxlen=self.realized_vol_window),
            "rv_slow_returns": deque(maxlen=max(self.realized_vol_window // self.tsrv_stride, 2)),
            "rv_sample_index": 0,
            "values": {},
        }

    def update(self, event: BarCloseEvent, state: dict[str, Any], context: FeatureContext) -> None:
        if not isinstance(event, BarCloseEvent):
            return

        state["bar_count"] += 1
        prev_close = state["prev_close"]
        true_range = (
            event.high - event.low
            if prev_close is None
            else max(event.high - event.low, abs(event.high - prev_close), abs(event.low - prev_close))
        )
        close_change = 0.0 if prev_close is None else event.close - prev_close
        gain = max(close_change, 0.0)
        loss = max(-close_change, 0.0)
        state["rv_sample_index"] += 1

        gk_term = compute_garman_klass_term(event.open, event.high, event.low, event.close)
        if gk_term is not None:
            state["gk_terms"].append(gk_term)
        if event.high > 0.0 and event.low > 0.0:
            log_hl = math.log(event.high / event.low) if event.low > 0.0 else 0.0
            state["pk_log_ranges_sq"].append(log_hl**2)
        if prev_close is not None and prev_close > 0.0 and event.close > 0.0:
            close_return = log_return(event.close, prev_close)
            state["rv_fast_returns"].append(close_return)
            if state["rv_sample_index"] % self.tsrv_stride == 0:
                state["rv_slow_returns"].append(close_return)
        if prev_close is not None and prev_close > 0.0 and event.open > 0.0:
            state["overnight_returns"].append(log_return(event.open, prev_close))
        if event.open > 0.0 and event.close > 0.0:
            state["open_close_returns"].append(log_return(event.close, event.open))

        for period in self.atr_periods:
            window = state["atr_windows"][period]
            window.append(true_range)
            previous_atr = state["atr_values"][period]
            if len(window) < period:
                state["atr_values"][period] = mean(list(window))
            elif previous_atr is None or len(window) == period and state["bar_count"] == period:
                state["atr_values"][period] = mean(list(window))
            else:
                state["atr_values"][period] = ((previous_atr * (period - 1)) + true_range) / period

        for period in self.rsi_periods:
            state["gain_windows"][period].append(gain)
            state["loss_windows"][period].append(loss)
            if state["avg_gain"][period] is None and len(state["gain_windows"][period]) == period:
                state["avg_gain"][period] = mean(list(state["gain_windows"][period]))
                state["avg_loss"][period] = mean(list(state["loss_windows"][period]))
            elif state["avg_gain"][period] is not None:
                state["avg_gain"][period] = ((state["avg_gain"][period] * (period - 1)) + gain) / period
                state["avg_loss"][period] = ((state["avg_loss"][period] * (period - 1)) + loss) / period

        all_close_periods = set(self.ladder_periods) | set(self.bollinger_periods)
        for period in all_close_periods:
            state["close_windows"][period].append(event.close)
        for period in self.ema_periods:
            previous_ema = state["ema_values"][period]
            alpha = 2.0 / (period + 1.0)
            state["ema_values"][period] = event.close if previous_ema is None else (alpha * event.close) + ((1 - alpha) * previous_ema)

        macd_line = None
        ema12 = state["ema_values"].get(12)
        ema26 = state["ema_values"].get(26)
        if ema12 is not None and ema26 is not None:
            macd_line = ema12 - ema26
            signal_alpha = 2.0 / (9.0 + 1.0)
            state["macd_signal"] = macd_line if state["macd_signal"] is None else (signal_alpha * macd_line) + ((1 - signal_alpha) * state["macd_signal"])

        bar_payload = {"high": event.high, "low": event.low, "close": event.close}
        for period in self.stochastic_periods:
            state["stoch_windows"][period].append(bar_payload)
            stochastic = compute_stochastic(list(state["stoch_windows"][period]), list(state["stoch_k_history"][period]))
            if stochastic is not None:
                state["stoch_k_history"][period].append(stochastic["k"])

        if state["prev_high"] is not None and state["prev_low"] is not None and prev_close is not None:
            up_move = event.high - state["prev_high"]
            down_move = state["prev_low"] - event.low
            plus_dm = up_move if up_move > down_move and up_move > 0 else 0.0
            minus_dm = down_move if down_move > up_move and down_move > 0 else 0.0
            adx_state = state["adx"]
            if adx_state["tr14"] is None:
                adx_state["tr_seed"].append(true_range)
                adx_state["plus_seed"].append(plus_dm)
                adx_state["minus_seed"].append(minus_dm)
                if len(adx_state["tr_seed"]) == self.adx_period:
                    adx_state["tr14"] = sum(adx_state["tr_seed"])
                    adx_state["plus_dm14"] = sum(adx_state["plus_seed"])
                    adx_state["minus_dm14"] = sum(adx_state["minus_seed"])
            else:
                adx_state["tr14"] = adx_state["tr14"] - (adx_state["tr14"] / self.adx_period) + true_range
                adx_state["plus_dm14"] = adx_state["plus_dm14"] - (adx_state["plus_dm14"] / self.adx_period) + plus_dm
                adx_state["minus_dm14"] = adx_state["minus_dm14"] - (adx_state["minus_dm14"] / self.adx_period) + minus_dm

            if adx_state["tr14"] not in (None, 0.0):
                adx_state["plus_di"] = 100.0 * safe_div(adx_state["plus_dm14"], adx_state["tr14"])
                adx_state["minus_di"] = 100.0 * safe_div(adx_state["minus_dm14"], adx_state["tr14"])
                dx = 100.0 * safe_div(abs(adx_state["plus_di"] - adx_state["minus_di"]), adx_state["plus_di"] + adx_state["minus_di"])
                if adx_state["adx"] is None:
                    adx_state["dx_seed"].append(dx)
                    if len(adx_state["dx_seed"]) == self.adx_period:
                        adx_state["adx"] = mean(list(adx_state["dx_seed"]))
                else:
                    adx_state["adx"] = ((adx_state["adx"] * (self.adx_period - 1)) + dx) / self.adx_period

        bollinger_payload: dict[str, Any] = {}
        for period in self.bollinger_periods:
            bands = compute_bollinger_bands(list(state["close_windows"][period]))
            if bands is not None:
                bollinger_payload[str(period)] = bands

        stochastic_payload: dict[str, Any] = {}
        for period in self.stochastic_periods:
            stochastic = compute_stochastic(list(state["stoch_windows"][period]), list(state["stoch_k_history"][period]))
            if stochastic is not None:
                stochastic_payload[str(period)] = stochastic

        realized_vol_gk = compute_realized_vol_gk(list(state["gk_terms"]), self.realized_vol_window)
        realized_vol_pk = compute_realized_vol_pk(list(state["pk_log_ranges_sq"]), self.realized_vol_window)
        realized_vol_yz = compute_realized_vol_yz(
            list(state["overnight_returns"]),
            list(state["open_close_returns"]),
            realized_vol_gk,
            self.realized_vol_window,
        )
        tsrv = compute_bar_tsrv(list(state["rv_fast_returns"]), list(state["rv_slow_returns"]), self.tsrv_stride)

        state["values"] = {
            "atr": {str(period): compute_atr(state["atr_values"][period]) for period in self.atr_periods},
            "bollinger": bollinger_payload,
            "rsi": {str(period): compute_rsi(state["avg_gain"][period], state["avg_loss"][period]) for period in self.rsi_periods},
            "macd": compute_macd(ema12, ema26, state["macd_signal"]),
            "ema": compute_ema_ladder(state["ema_values"]),
            "sma": compute_sma_ladder(state["close_windows"]),
            "stochastic": stochastic_payload,
            "adx": compute_adx(state["adx"]["adx"], state["adx"]["plus_di"], state["adx"]["minus_di"]),
            "realized_vol_gk": realized_vol_gk,
            "realized_vol_yz": realized_vol_yz,
            "realized_vol_pk": realized_vol_pk,
            "realized_volatility": {
                "gk": realized_vol_gk,
                "yz": realized_vol_yz,
                "pk": realized_vol_pk,
                "tsrv": tsrv,
            },
            "tsrv": tsrv,
        }

        state["prev_close"] = event.close
        state["prev_high"] = event.high
        state["prev_low"] = event.low

    def ready(self, state: dict[str, Any]) -> bool:
        return state["bar_count"] >= self.warmup_periods

    def value(self, state: dict[str, Any] | None = None) -> dict[str, Any]:
        return dict((self._standalone_state if state is None else state)["values"])
