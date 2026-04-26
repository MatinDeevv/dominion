from __future__ import annotations

import pytest

from tests.task_helpers import make_tick


def test_hawkes_imbalance_matches_exposed_intensity_ratio() -> None:
    from aphelion.feature_engine.features import MicrostructureFeature

    feature = MicrostructureFeature()
    price = 100.0
    feature.on_tick(make_tick(1, 1_000_000_000, last=price))
    for idx in range(2, 202):
        price += 1.0 if idx % 3 else -0.5
        feature.on_tick(make_tick(idx, idx * 1_000_000_000, last=price))
    values = feature.value()
    expected = (values["ms_hawkes_buy_intensity"] - values["ms_hawkes_sell_intensity"]) / (
        values["ms_hawkes_buy_intensity"] + values["ms_hawkes_sell_intensity"] + 1e-9
    )
    assert values["ms_hawkes_imbalance"] == pytest.approx(expected, abs=1e-9)
