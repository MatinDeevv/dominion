from __future__ import annotations

import numpy as np

from tests.task_helpers import make_bar, sine_prices


def test_fractal_dimension_is_lower_for_sine_wave_than_noise() -> None:
    from aphelion.feature_engine.features import MicrostructureFeature

    feature = MicrostructureFeature(default_timeframe="1m")
    for idx, close in enumerate(sine_prices(100), start=1):
        feature.on_bar(make_bar(idx, idx * 60_000_000_000, close=close, open_price=close, high=close + 0.2, low=close - 0.2))
    assert feature.value()["ms_fractal_dimension"] < 1.5


def test_fractal_dimension_is_higher_for_white_noise() -> None:
    from aphelion.feature_engine.features import MicrostructureFeature

    rng = np.random.default_rng(19)
    feature = MicrostructureFeature(default_timeframe="1m")
    noise = 1900.0 + rng.normal(0.0, 5.0, size=100)
    for idx, close in enumerate(noise, start=1):
        feature.on_bar(make_bar(idx, idx * 60_000_000_000, close=float(close), open_price=float(close), high=float(close) + 0.2, low=float(close) - 0.2))
    assert feature.value()["ms_fractal_dimension"] > 1.5
