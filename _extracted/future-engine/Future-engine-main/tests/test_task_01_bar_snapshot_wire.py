from __future__ import annotations

from tests.task_helpers import build_microstructure_engine, make_bar, make_tick


def test_bar_snapshot_contains_cached_microstructure_values() -> None:
    engine = build_microstructure_engine(window=10, bucket_volume=25.0)
    for seq_no in range(1, 51):
        engine.on_event(make_tick(seq_no, seq_no * 1_000_000_000, last=1900.0 + seq_no * 0.1, volume=5.0))
    snapshots = engine.on_event(make_bar(100, 100 * 1_000_000_000, close=1906.0))
    snapshot = snapshots[-1]
    assert snapshot.features["ms_vpin"] is not None
    assert snapshot.features["ms_toxicity"] is not None
    assert snapshot.features["ms_ofi"] is not None


def test_bar_snapshot_reuses_previous_microstructure_when_no_new_ticks_arrive() -> None:
    engine = build_microstructure_engine(window=10, bucket_volume=25.0)
    for seq_no in range(1, 31):
        engine.on_event(make_tick(seq_no, seq_no * 1_000_000_000, last=1900.0 + seq_no * 0.05, volume=5.0))
    first_snapshot = engine.on_event(make_bar(100, 100 * 1_000_000_000, close=1901.0))[-1]
    second_snapshot = engine.on_event(make_bar(101, 101 * 1_000_000_000, close=1901.5))[-1]
    assert second_snapshot.features["ms_vpin"] == first_snapshot.features["ms_vpin"]
    assert second_snapshot.features["ms_toxicity"] == first_snapshot.features["ms_toxicity"]
    assert second_snapshot.features["ms_ofi"] == first_snapshot.features["ms_ofi"]


def test_bar_snapshot_updates_between_bars_and_does_not_stay_stale() -> None:
    engine = build_microstructure_engine(window=10, bucket_volume=20.0)
    for seq_no in range(1, 21):
        engine.on_event(make_tick(seq_no, seq_no * 1_000_000_000, last=1900.0 + seq_no * 0.1, volume=4.0))
    first_snapshot = engine.on_event(make_bar(100, 100 * 1_000_000_000, close=1902.0))[-1]

    for seq_no in range(101, 121):
        engine.on_event(make_tick(seq_no, seq_no * 1_000_000_000, last=1910.0 - seq_no * 0.08, volume=8.0))
    second_snapshot = engine.on_event(make_bar(121, 121 * 1_000_000_000, close=1903.0))[-1]

    assert second_snapshot.features["ms_ofi"] != first_snapshot.features["ms_ofi"]
    assert second_snapshot.features["ms_vpin"] != first_snapshot.features["ms_vpin"]
