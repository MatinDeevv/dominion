from __future__ import annotations

import pytest

from tests.task_helpers import make_tick


def test_vrp_and_implied_vol_are_none_when_no_implied_vol_ticks_are_seen() -> None:
    from aphelion.feature_engine.features import MicrostructureFeature

    feature = MicrostructureFeature(window=8, bucket_volume=20.0)
    for idx in range(1, 6):
        feature.on_tick(make_tick(idx, idx * 1_000_000_000, last=1900.0 + idx * 0.1))
    values = feature.value()
    assert values["ms_vrp"] is None
    assert values["ms_implied_vol"] is None


def test_vrp_uses_last_implied_vol_minus_realized_vol_gk() -> None:
    from aphelion.feature_engine.features import MicrostructureFeature

    feature = MicrostructureFeature(window=8, bucket_volume=20.0)
    feature.set_realized_volatility(0.10)
    feature.on_tick(make_tick(1, 1_000_000_000, last=1900.1, implied_vol=0.15))
    assert feature.value()["ms_vrp"] == pytest.approx(0.05, abs=1e-6)


def test_vrp_retains_last_known_implied_vol_when_subsequent_ticks_omit_it() -> None:
    from aphelion.feature_engine.features import MicrostructureFeature

    feature = MicrostructureFeature(window=8, bucket_volume=20.0)
    feature.set_realized_volatility(0.10)
    feature.on_tick(make_tick(1, 1_000_000_000, last=1900.1, implied_vol=0.15))
    feature.on_tick(make_tick(2, 2_000_000_000, last=1900.2))
    values = feature.value()
    assert values["ms_implied_vol"] == pytest.approx(0.15, abs=1e-12)
    assert values["ms_vrp"] == pytest.approx(0.05, abs=1e-6)
