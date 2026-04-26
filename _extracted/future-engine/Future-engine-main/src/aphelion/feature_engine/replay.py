from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .engine import FeatureEngine
from .events import event_from_record
from .snapshot import FeatureSnapshot


def replay_from_journal(records: Iterable[dict], engine: FeatureEngine) -> list[FeatureSnapshot]:
    snapshots: list[FeatureSnapshot] = []
    for record in records:
        event = event_from_record(record)
        snapshots.extend(engine.on_event(event))
    return snapshots


def replay_from_jsonl(path: str | Path, engine: FeatureEngine) -> list[FeatureSnapshot]:
    snapshots: list[FeatureSnapshot] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            event = event_from_record(record)
            snapshots.extend(engine.on_event(event))
    return snapshots


def export_engine_state(engine: FeatureEngine) -> dict:
    return engine.export_engine_state()


def restore_engine_state(engine: FeatureEngine, payload: dict) -> None:
    engine.restore_engine_state(payload)

