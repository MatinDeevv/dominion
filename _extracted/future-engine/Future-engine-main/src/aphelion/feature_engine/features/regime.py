from __future__ import annotations

import math
from collections import deque
from typing import Any, Sequence

from ..events import BarCloseEvent
from ..utils import clamp, correlation, log_return, mean, safe_div, stddev
from .base import FeatureContext, RegimeFeature


REGIME_LABELS = ("trending", "mean_reverting", "volatile")


def compute_hmm_state_probabilities(
    returns: Sequence[float],
    previous_probabilities: dict[str, float],
    transition_matrix: dict[str, dict[str, float]],
    *,
    volatility_scale: float = 0.01,
) -> dict[str, float]:
    if not returns:
        uniform = 1.0 / len(REGIME_LABELS)
        return {label: uniform for label in REGIME_LABELS}

    volatility = stddev(list(returns))
    drift = mean(list(returns))
    trend_strength = safe_div(abs(drift), max(volatility, 1e-9))
    lagged_autocorr = correlation(list(returns[:-1]), list(returns[1:])) if len(returns) > 2 else 0.0

    emissions = {
        "trending": math.exp(clamp(1.25 * trend_strength + max(lagged_autocorr, 0.0), -20.0, 20.0)),
        "mean_reverting": math.exp(
            clamp(max(-lagged_autocorr, 0.0) * 1.5 + max(1.0 - trend_strength, 0.0), -20.0, 20.0)
        ),
        "volatile": math.exp(clamp(safe_div(volatility, max(volatility_scale, 1e-9)), -20.0, 20.0)),
    }

    next_probabilities: dict[str, float] = {}
    for target_state in REGIME_LABELS:
        transition_mass = sum(
            previous_probabilities[source_state] * transition_matrix[source_state][target_state]
            for source_state in REGIME_LABELS
        )
        next_probabilities[target_state] = emissions[target_state] * transition_mass

    normalizer = sum(next_probabilities.values()) or 1.0
    return {state: value / normalizer for state, value in next_probabilities.items()}


def compute_regime_duration(current_state: str, previous_state: str | None, previous_duration: int) -> int:
    return previous_duration + 1 if current_state == previous_state else 1


def compute_transition_probabilities(transition_counts: dict[str, dict[str, int]]) -> dict[str, dict[str, float]]:
    probabilities: dict[str, dict[str, float]] = {}
    for source_state, targets in transition_counts.items():
        total = sum(targets.values()) or 1
        probabilities[source_state] = {target_state: count / total for target_state, count in targets.items()}
    return probabilities


def compute_hurst_exponent(closes: Sequence[float], window: int) -> float:
    if len(closes) < window:
        return 0.5
    returns = [log_return(current, previous) for previous, current in zip(closes[:-1], closes[1:])]
    if not returns:
        return 0.5
    avg_return = mean(returns)
    demeaned = [value - avg_return for value in returns]
    cumulative = []
    running = 0.0
    for value in demeaned:
        running += value
        cumulative.append(running)
    rescaled_range = max(cumulative) - min(cumulative)
    sigma = stddev(returns)
    if sigma <= 1e-12 or rescaled_range <= 0.0:
        return 0.5
    hurst = math.log(rescaled_range / sigma) / math.log(window)
    return clamp(hurst, 0.0, 1.0)


class RegimeStateFeature(RegimeFeature):
    def __init__(
        self,
        *,
        name: str = "regime",
        version: str = "1.0.0",
        window: int = 64,
        hurst_window: int = 100,
        default_timeframe: str = "1h",
    ) -> None:
        super().__init__(
            name=name,
            version=version,
            default_timeframe=default_timeframe,
            warmup_periods=max(window, hurst_window),
        )
        self.window = window
        self.hurst_window = hurst_window
        self.transition_matrix = {
            "trending": {"trending": 0.88, "mean_reverting": 0.07, "volatile": 0.05},
            "mean_reverting": {"trending": 0.08, "mean_reverting": 0.84, "volatile": 0.08},
            "volatile": {"trending": 0.10, "mean_reverting": 0.10, "volatile": 0.80},
        }
        self._standalone_state = self.initialize_state()

    def on_bar(self, event: BarCloseEvent) -> None:
        self.update(event, self._standalone_state, FeatureContext(object(), event.symbol, event, event.timeframe))

    def warmup_complete(self) -> bool:
        return self.ready(self._standalone_state)

    def initialize_state(self) -> dict[str, Any]:
        uniform = 1.0 / len(REGIME_LABELS)
        return {
            "prev_close": None,
            "returns": deque(maxlen=self.window),
            "closes": deque(maxlen=self.hurst_window),
            "probabilities": {label: uniform for label in REGIME_LABELS},
            "current_state": None,
            "duration": 0,
            "transition_counts": {
                source: {target: 0 for target in REGIME_LABELS} for source in REGIME_LABELS
            },
            "values": {},
        }

    def update(self, event: BarCloseEvent, state: dict[str, Any], context: FeatureContext) -> None:
        if not isinstance(event, BarCloseEvent):
            return

        prev_close = state["prev_close"]
        if prev_close is not None and prev_close > 0:
            state["returns"].append(log_return(event.close, prev_close))
        state["closes"].append(event.close)

        probabilities = compute_hmm_state_probabilities(
            list(state["returns"]),
            state["probabilities"],
            self.transition_matrix,
        )
        state["probabilities"] = probabilities
        current_state = max(probabilities, key=probabilities.get)
        previous_state = state["current_state"]
        if previous_state is not None:
            state["transition_counts"][previous_state][current_state] += 1
        state["duration"] = compute_regime_duration(current_state, previous_state, state["duration"])
        state["current_state"] = current_state
        transition_probabilities = compute_transition_probabilities(state["transition_counts"])
        state["values"] = {
            "probabilities": probabilities,
            "current_state": current_state,
            "regime_duration": state["duration"],
            "transition_probabilities": transition_probabilities,
            "hurst_exponent": compute_hurst_exponent(list(state["closes"]), self.hurst_window),
        }
        state["prev_close"] = event.close

    def ready(self, state: dict[str, Any]) -> bool:
        return len(state["returns"]) >= self.warmup_periods

    def value(self, state: dict[str, Any] | None = None) -> dict[str, Any]:
        return dict((self._standalone_state if state is None else state)["values"])
