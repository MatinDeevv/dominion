from __future__ import annotations

from tests.task_helpers import make_tick


def test_quote_stuffing_flag_trips_after_large_tick_rate_spike() -> None:
    from aphelion.feature_engine.features import MicrostructureFeature

    feature = MicrostructureFeature()
    seq_no = 1
    for second in range(100):
        for tick_idx in range(5):
            feature.on_tick(make_tick(seq_no, second * 1_000_000_000 + tick_idx, last=100.0 + seq_no * 0.001))
            seq_no += 1
    for tick_idx in range(1000):
        feature.on_tick(make_tick(seq_no, 100 * 1_000_000_000 + tick_idx, last=101.0 + tick_idx * 0.0001))
        seq_no += 1
    values = feature.value()
    assert values["ms_tick_rate_current"] == 1000
    assert values["ms_quote_stuffing_flag"] is True


def test_quote_stuffing_flag_stays_false_without_enough_history() -> None:
    from aphelion.feature_engine.features import MicrostructureFeature

    feature = MicrostructureFeature()
    seq_no = 1
    for second in range(50):
        for tick_idx in range(5):
            feature.on_tick(make_tick(seq_no, second * 1_000_000_000 + tick_idx, last=100.0 + seq_no * 0.001))
            seq_no += 1
    for tick_idx in range(1000):
        feature.on_tick(make_tick(seq_no, 50 * 1_000_000_000 + tick_idx, last=101.0 + tick_idx * 0.0001))
        seq_no += 1
    assert feature.value()["ms_quote_stuffing_flag"] is False
