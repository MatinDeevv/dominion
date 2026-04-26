from __future__ import annotations

import pytest

from tests.task_helpers import make_tick


def test_vpin_bucket_volume_calibrates_and_recalibrates_to_new_regime() -> None:
    from aphelion.feature_engine.features import MicrostructureFeature

    feature = MicrostructureFeature(window=10, bucket_volume=500.0)
    historical = [make_tick(idx, idx * 1_000_000_000, volume=100.0 + (idx % 5) - 2) for idx in range(1, 501)]
    feature.calibrate(historical)
    assert feature.value()["ms_vpin_bucket_volume"] == pytest.approx(100.0, rel=0.05)

    for idx in range(501, 1001):
        feature.on_tick(make_tick(idx, idx * 1_000_000_000, last=1900.0 + idx * 0.01, volume=200.0 + (idx % 7) - 3))
    assert feature.value()["ms_vpin_bucket_volume"] == pytest.approx(200.0, rel=0.1)


def test_vpin_bucket_volume_adapts_within_five_hundred_ticks_after_regime_shift() -> None:
    from aphelion.feature_engine.features import MicrostructureFeature

    feature = MicrostructureFeature(window=10, bucket_volume=500.0)
    for idx in range(1, 501):
        feature.on_tick(make_tick(idx, idx * 1_000_000_000, last=1900.0 + idx * 0.01, volume=100.0))
    original = feature.value()["ms_vpin_bucket_volume"]

    for idx in range(501, 1001):
        feature.on_tick(make_tick(idx, idx * 1_000_000_000, last=1905.0 + idx * 0.01, volume=200.0))
    shifted = feature.value()["ms_vpin_bucket_volume"]

    assert shifted > original * 1.5
