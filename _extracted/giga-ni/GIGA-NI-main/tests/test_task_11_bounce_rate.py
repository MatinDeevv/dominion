from __future__ import annotations

import pytest

from tests.task_helpers import make_tick


def test_bounce_rate_is_one_for_perfect_alternation() -> None:
    from aphelion.feature_engine.features import MicrostructureFeature

    feature = MicrostructureFeature()
    price = 100.0
    feature.on_tick(make_tick(1, 1_000_000_000, last=price))
    for idx in range(2, 66):
        price += 1.0 if idx % 2 == 0 else -1.0
        feature.on_tick(make_tick(idx, idx * 1_000_000_000, last=price))
    assert feature.value()["ms_bounce_rate_64"] == pytest.approx(1.0, abs=0.02)


def test_bounce_rate_is_zero_for_one_sided_directional_flow() -> None:
    from aphelion.feature_engine.features import MicrostructureFeature

    feature = MicrostructureFeature()
    price = 100.0
    feature.on_tick(make_tick(1, 1_000_000_000, last=price))
    for idx in range(2, 66):
        price += 1.0
        feature.on_tick(make_tick(idx, idx * 1_000_000_000, last=price))
    assert feature.value()["ms_bounce_rate_64"] == pytest.approx(0.0, abs=0.02)
