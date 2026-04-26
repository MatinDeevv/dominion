from __future__ import annotations

import numpy as np

from tests.task_helpers import build_regime_feature, make_bar


def test_hurst_exponent_is_high_for_trending_series() -> None:
    rng = np.random.default_rng(7)
    returns = []
    prev = 0.003
    for _ in range(150):
        prev = 0.85 * prev + rng.normal(0.0, 0.0005)
        returns.append(prev + 0.0015)
    price = 1900.0
    feature = build_regime_feature(window=20, hurst_window=100)
    for idx, ret in enumerate(returns, start=1):
        price *= np.exp(ret)
        feature.on_bar(make_bar(idx, idx * 3_600_000_000_000, timeframe="1h", open_price=price * 0.999, high=price * 1.001, low=price * 0.998, close=price))
    assert feature.value()["hurst_exponent"] > 0.55


def test_hurst_exponent_is_low_for_mean_reverting_series() -> None:
    rng = np.random.default_rng(11)
    price = 1900.0
    feature = build_regime_feature(window=20, hurst_window=100)
    for idx in range(1, 151):
        shock = rng.normal(0.0, 0.8)
        price += 0.35 * (1900.0 - price) + shock
        feature.on_bar(make_bar(idx, idx * 3_600_000_000_000, timeframe="1h", open_price=price - 0.4, high=price + 0.8, low=price - 0.8, close=price))
    assert feature.value()["hurst_exponent"] < 0.45


def test_hurst_exponent_is_near_half_for_iid_random_walk() -> None:
    rng = np.random.default_rng(23)
    price = 1900.0
    feature = build_regime_feature(window=20, hurst_window=100)
    for idx in range(1, 101):
        price *= np.exp(rng.normal(0.0, 0.002))
        feature.on_bar(make_bar(idx, idx * 3_600_000_000_000, timeframe="1h", open_price=price * 0.999, high=price * 1.001, low=price * 0.998, close=price))
    hurst = feature.value()["hurst_exponent"]
    assert 0.3 <= hurst <= 0.7
