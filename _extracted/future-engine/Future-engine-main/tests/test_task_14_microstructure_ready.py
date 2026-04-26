from __future__ import annotations

from tests.task_helpers import build_microstructure_engine, make_bar, make_tick


def test_microstructure_ready_is_false_before_first_vpin_bucket_completes() -> None:
    engine = build_microstructure_engine(window=5, bucket_volume=1000.0)
    for seq_no in range(1, 11):
        engine.on_event(make_tick(seq_no, seq_no * 1_000_000_000, last=1900.0 + seq_no * 0.1, volume=5.0))
    snapshot = engine.on_event(make_bar(100, 100 * 1_000_000_000, close=1902.0))[-1]
    assert snapshot.metadata["ms_microstructure_ready"] is False


def test_microstructure_ready_is_true_after_warmup_and_bucket_completion() -> None:
    engine = build_microstructure_engine(window=5, bucket_volume=20.0)
    for seq_no in range(1, 11):
        engine.on_event(make_tick(seq_no, seq_no * 1_000_000_000, last=1900.0 + seq_no * 0.1, volume=5.0))
    snapshot = engine.on_event(make_bar(100, 100 * 1_000_000_000, close=1902.0))[-1]
    assert snapshot.features["ms_vpin_buckets_completed"] >= 1
    assert snapshot.metadata["ms_microstructure_ready"] is True
