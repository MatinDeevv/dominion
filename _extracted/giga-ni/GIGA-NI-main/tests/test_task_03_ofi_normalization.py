from __future__ import annotations

import math

import pytest

from tests.task_helpers import make_tick


def test_ofi_zscore_100_is_active_before_500_tick_window_is_ready() -> None:
    from aphelion.feature_engine.features import MicrostructureFeature

    feature = MicrostructureFeature(window=16, bucket_volume=100.0)
    for idx in range(1, 201):
        feature.on_tick(
            make_tick(
                idx,
                idx * 1_000_000_000,
                last=1900.0 + idx * 0.05,
                bid_size=float((idx % 5) + 1),
                ask_size=1.0,
            )
        )
    values = feature.value()
    assert values["ms_ofi_zscore_100"] != 0.0
    assert values["ms_ofi_zscore_500"] == 0.0
    assert values["ms_ofi_normalized"] == values["ms_ofi_zscore_100"]


def test_ofi_zscore_windows_are_non_zero_and_finite_after_six_hundred_ticks() -> None:
    from aphelion.feature_engine.features import MicrostructureFeature

    feature = MicrostructureFeature(window=16, bucket_volume=100.0)
    for idx in range(1, 601):
        feature.on_tick(
            make_tick(
                idx,
                idx * 1_000_000_000,
                last=1900.0 + idx * 0.05,
                bid_size=float((idx % 7) + 1),
                ask_size=1.0,
            )
        )
    values = feature.value()
    assert values["ms_ofi_zscore_100"] != 0.0
    assert values["ms_ofi_zscore_500"] != 0.0
    assert math.isfinite(values["ms_ofi_zscore_100"])
    assert math.isfinite(values["ms_ofi_zscore_500"])


def test_ofi_zscores_are_zero_when_raw_ofi_equals_rolling_mean() -> None:
    from aphelion.feature_engine.features import MicrostructureFeature

    feature = MicrostructureFeature(window=16, bucket_volume=100.0)
    for idx in range(1, 601):
        feature.on_tick(
            make_tick(
                idx,
                idx * 1_000_000_000,
                last=1900.0 + idx * 0.05,
                bid_size=3.0,
                ask_size=1.0,
            )
        )
    values = feature.value()
    assert values["ms_ofi_zscore_100"] == pytest.approx(0.0, abs=1e-6)
    assert values["ms_ofi_zscore_500"] == pytest.approx(0.0, abs=1e-6)
