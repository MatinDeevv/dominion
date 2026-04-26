from __future__ import annotations

from tests.task_helpers import make_tick


def test_tick_run_resets_to_one_on_direction_change() -> None:
    from aphelion.feature_engine.features import MicrostructureFeature

    feature = MicrostructureFeature()
    feature.on_tick(make_tick(1, 1_000_000_000, last=100.0))
    for idx in range(2, 7):
        feature.on_tick(make_tick(idx, idx * 1_000_000_000, last=100.0 + (idx - 1)))
    feature.on_tick(make_tick(7, 7_000_000_000, last=104.0))
    values = feature.value()
    assert values["ms_tick_run_length"] == 1
    assert values["ms_tick_run_direction"] == -1


def test_tick_run_counts_consecutive_up_ticks() -> None:
    from aphelion.feature_engine.features import MicrostructureFeature

    feature = MicrostructureFeature()
    feature.on_tick(make_tick(1, 1_000_000_000, last=100.0))
    for idx in range(2, 12):
        feature.on_tick(make_tick(idx, idx * 1_000_000_000, last=99.0 + idx))
    values = feature.value()
    assert values["ms_tick_run_length"] == 10
    assert values["ms_tick_run_direction"] == 1


def test_neutral_tick_does_not_break_or_extend_existing_run() -> None:
    from aphelion.feature_engine.features import MicrostructureFeature

    feature = MicrostructureFeature()
    feature.on_tick(make_tick(1, 1_000_000_000, last=100.0))
    feature.on_tick(make_tick(2, 2_000_000_000, last=101.0))
    feature.on_tick(make_tick(3, 3_000_000_000, last=102.0))
    feature.on_tick(make_tick(4, 4_000_000_000, last=102.0))
    feature.on_tick(make_tick(5, 5_000_000_000, last=103.0))
    values = feature.value()
    assert values["ms_tick_run_length"] == 2
    assert values["ms_tick_run_direction"] == 1
