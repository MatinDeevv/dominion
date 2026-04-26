from __future__ import annotations

import argparse
import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

import pyarrow.parquet as pq
import yaml

from ..engine import FeatureEngine, FeatureEngineConfig
from ..events import BarCloseEvent, CrossAssetBarEvent, SessionEvent, TickEvent
from ..features import (
    CrossAssetRelationshipFeature,
    MarketStructureFeature,
    MicrostructureFeature,
    RegimeStateFeature,
    SessionCalendarFeature,
    TechnicalFeature,
    VolumeProfileFeature,
    VWAPFeature,
)
from ..journal import JsonlJournal
from ..registry import FeatureRegistry
from ..snapshot import FeatureSnapshot


MT5PIPE_TO_ENGINE_TIMEFRAME = {
    "M1": "1m",
    "M2": "2m",
    "M3": "3m",
    "M4": "4m",
    "M5": "5m",
    "M6": "6m",
    "M10": "10m",
    "M12": "12m",
    "M15": "15m",
    "M20": "20m",
    "M30": "30m",
    "H1": "1h",
    "H2": "2h",
    "H3": "3h",
    "H4": "4h",
    "H6": "6h",
    "H8": "8h",
    "H12": "12h",
    "D1": "1d",
    "W1": "1w",
    "MN1": "1mo",
}


def _tf_delta(tf: str, bar_start: dt.datetime) -> dt.timedelta:
    if tf.startswith("M") and tf != "MN1":
        return dt.timedelta(minutes=int(tf[1:]))
    if tf.startswith("H"):
        return dt.timedelta(hours=int(tf[1:]))
    if tf == "D1":
        return dt.timedelta(days=1)
    if tf == "W1":
        return dt.timedelta(weeks=1)
    if tf == "MN1":
        year = bar_start.year + (1 if bar_start.month == 12 else 0)
        month = 1 if bar_start.month == 12 else bar_start.month + 1
        next_month = bar_start.replace(year=year, month=month, day=1, hour=0, minute=0, second=0, microsecond=0)
        return next_month - bar_start
    raise ValueError(f"Unsupported MT5Pipe timeframe: {tf}")


def normalize_mt5pipe_timeframe(timeframe: str) -> str:
    normalized = MT5PIPE_TO_ENGINE_TIMEFRAME.get(timeframe.upper())
    if normalized is None:
        raise ValueError(f"Unsupported MT5Pipe timeframe: {timeframe}")
    return normalized


def _date_range(start_date: dt.date, end_date: dt.date) -> Iterator[dt.date]:
    current = start_date
    while current <= end_date:
        yield current
        current += dt.timedelta(days=1)


def _parquet_files(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    return sorted(directory.glob("**/*.parquet"))


def _read_parquet_rows(directory: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for file_path in _parquet_files(directory):
        table = pq.ParquetFile(file_path).read()
        rows.extend(table.to_pylist())
    return rows


def _as_utc_datetime(value: Any) -> dt.datetime:
    if isinstance(value, dt.datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=dt.timezone.utc)
        return value.astimezone(dt.timezone.utc)
    if isinstance(value, str):
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(dt.timezone.utc)
    raise TypeError(f"Unsupported datetime value: {value!r}")


def _to_ns(value: dt.datetime) -> int:
    return int(value.timestamp() * 1_000_000_000)


def resolve_mt5pipe_storage_root(
    *,
    mt5pipe_root: Path,
    pipeline_config_path: Path | None = None,
    explicit_storage_root: Path | None = None,
) -> Path:
    if explicit_storage_root is not None:
        return explicit_storage_root
    config_path = pipeline_config_path or (mt5pipe_root / "config" / "pipeline.yaml")
    if not config_path.exists():
        return mt5pipe_root / "data" / "local_data" / "pipeline_data"
    with config_path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    root_value = ((payload.get("storage") or {}).get("root")) or "data/local_data/pipeline_data"
    resolved = Path(root_value)
    if not resolved.is_absolute():
        resolved = (mt5pipe_root / resolved).resolve()
    return resolved


def _session_flags(ts_utc: dt.datetime) -> dict[str, bool]:
    hour = ts_utc.hour
    return {
        "asian": 0 <= hour < 8,
        "london": 7 <= hour < 16,
        "new_york": 13 <= hour < 22,
    }


def infer_session_events(
    *,
    symbol: str,
    timestamps: Sequence[dt.datetime],
    starting_seq_no: int = 0,
) -> list[SessionEvent]:
    previous_flags = {"asian": False, "london": False, "new_york": False}
    events: list[SessionEvent] = []
    seq_no = starting_seq_no
    for ts_utc in sorted(timestamps):
        flags = _session_flags(ts_utc)
        for session_name in ("asian", "london", "new_york"):
            if flags[session_name] and not previous_flags[session_name]:
                seq_no += 1
                events.append(
                    SessionEvent(
                        seq_no=seq_no,
                        ts_event_ns=_to_ns(ts_utc),
                        symbol=symbol,
                        session_name=session_name,
                        session_state="open",
                    )
                )
            elif previous_flags[session_name] and not flags[session_name]:
                seq_no += 1
                events.append(
                    SessionEvent(
                        seq_no=seq_no,
                        ts_event_ns=_to_ns(ts_utc),
                        symbol=symbol,
                        session_name=session_name,
                        session_state="close",
                    )
                )
        previous_flags = flags
    return events


@dataclass(frozen=True, slots=True)
class MT5PipeReplayConfig:
    mt5pipe_root: Path
    primary_symbol: str
    start_date: dt.date
    end_date: dt.date
    tick_symbols: tuple[str, ...] = ("XAUUSD",)
    bar_symbols: tuple[str, ...] = ("XAUUSD",)
    bar_timeframes: tuple[str, ...] = ("M1", "M15", "H1")
    storage_root: Path | None = None
    pipeline_config_path: Path | None = None
    event_journal_path: Path | None = None
    snapshot_journal_path: Path | None = None
    include_inferred_sessions: bool = True
    emit_tick_snapshots: bool = False
    include_btc: bool = False


@dataclass(frozen=True, slots=True)
class _PendingEvent:
    ts_event_ns: int
    priority: int
    stable_key: str
    payload: dict[str, Any]


def load_mt5pipe_events(config: MT5PipeReplayConfig) -> list[TickEvent | BarCloseEvent | CrossAssetBarEvent | SessionEvent]:
    storage_root = resolve_mt5pipe_storage_root(
        mt5pipe_root=config.mt5pipe_root,
        pipeline_config_path=config.pipeline_config_path,
        explicit_storage_root=config.storage_root,
    )
    pending: list[_PendingEvent] = []

    for symbol in config.tick_symbols:
        for date_value in _date_range(config.start_date, config.end_date):
            rows = _read_parquet_rows(storage_root / "canonical_ticks" / f"symbol={symbol}" / f"date={date_value.isoformat()}")
            for index, row in enumerate(rows):
                ts_utc = _as_utc_datetime(row["ts_utc"])
                ts_event_ns = _to_ns(ts_utc)
                pending.append(
                    _PendingEvent(
                        ts_event_ns=ts_event_ns,
                        priority=10,
                        stable_key=f"tick|{symbol}|{date_value.isoformat()}|{index:09d}",
                        payload={
                            "kind": "tick",
                            "symbol": symbol,
                            "ts_event_ns": ts_event_ns,
                            "ts_receive_ns": ts_event_ns,
                            "bid": float(row["bid"]),
                            "ask": float(row["ask"]),
                            "last": float(row.get("last", 0.0) or 0.0),
                            "volume": float(row.get("volume", 0.0) or 0.0),
                            "source": str(row.get("source_primary", "mt5pipe")),
                        },
                    )
                )

    bar_start_times_for_sessions: list[dt.datetime] = []
    for symbol in config.bar_symbols:
        for mt5pipe_timeframe in config.bar_timeframes:
            for date_value in _date_range(config.start_date, config.end_date):
                rows = _read_parquet_rows(
                    storage_root / "bars" / f"symbol={symbol}" / f"timeframe={mt5pipe_timeframe}" / f"date={date_value.isoformat()}"
                )
                for index, row in enumerate(rows):
                    bar_start_utc = _as_utc_datetime(row["time_utc"])
                    bar_close_utc = bar_start_utc + _tf_delta(mt5pipe_timeframe, bar_start_utc)
                    if symbol == config.primary_symbol and mt5pipe_timeframe == "M1":
                        bar_start_times_for_sessions.append(bar_start_utc)
                    pending.append(
                        _PendingEvent(
                            ts_event_ns=_to_ns(bar_close_utc),
                            priority=20,
                            stable_key=f"bar|{symbol}|{mt5pipe_timeframe}|{date_value.isoformat()}|{index:09d}",
                            payload={
                                "kind": "bar",
                                "symbol": symbol,
                                "timeframe": normalize_mt5pipe_timeframe(mt5pipe_timeframe),
                                "open": float(row["open"]),
                                "high": float(row["high"]),
                                "low": float(row["low"]),
                                "close": float(row["close"]),
                                "volume": float(row.get("volume_sum", 0.0) or 0.0),
                                "tick_count": int(row.get("tick_count", 0) or 0),
                                "vwap": None,
                            },
                        )
                    )

    if config.include_inferred_sessions:
        for event in infer_session_events(symbol=config.primary_symbol, timestamps=bar_start_times_for_sessions):
            pending.append(
                _PendingEvent(
                    ts_event_ns=event.ts_event_ns,
                    priority=5,
                    stable_key=f"session|{event.session_name}|{event.ts_event_ns}",
                    payload={
                        "kind": "session",
                        "symbol": event.symbol,
                        "session_name": event.session_name,
                        "session_state": event.session_state,
                    },
                )
            )

    ordered = sorted(pending, key=lambda item: (item.ts_event_ns, item.priority, item.stable_key))
    materialized: list[TickEvent | BarCloseEvent | CrossAssetBarEvent | SessionEvent] = []
    for seq_no, item in enumerate(ordered, start=1):
        payload = dict(item.payload)
        kind = payload.pop("kind")
        if kind == "tick":
            materialized.append(TickEvent(seq_no=seq_no, **payload))
        elif kind == "session":
            materialized.append(SessionEvent(seq_no=seq_no, ts_event_ns=item.ts_event_ns, **payload))
        elif kind == "bar":
            event_cls = BarCloseEvent if payload["symbol"] == config.primary_symbol else CrossAssetBarEvent
            materialized.append(event_cls(seq_no=seq_no, ts_event_ns=item.ts_event_ns, **payload))
        else:
            raise ValueError(f"Unsupported pending event kind: {kind}")
    return materialized


def replay_mt5pipe_into_engine(
    config: MT5PipeReplayConfig,
    *,
    engine: FeatureEngine | None = None,
) -> list[FeatureSnapshot]:
    if engine is None:
        registry = FeatureRegistry()
        registry.register(MicrostructureFeature(default_timeframe="1m"))
        registry.register(VolumeProfileFeature(default_timeframe="1m"))
        registry.register(VWAPFeature(default_timeframe="1m"))
        registry.register(TechnicalFeature(default_timeframe="1m"))
        registry.register(SessionCalendarFeature(default_timeframe="1m"))
        registry.register(MarketStructureFeature(default_timeframe="15m"))
        registry.register(RegimeStateFeature(default_timeframe="1h"))
        if any(symbol != config.primary_symbol for symbol in config.bar_symbols):
            registry.register(
                CrossAssetRelationshipFeature(
                    primary_symbol=config.primary_symbol,
                    include_btc=config.include_btc,
                    default_timeframe="1h",
                )
            )
        engine = FeatureEngine(
            registry=registry,
            config=FeatureEngineConfig(
                primary_symbol=config.primary_symbol,
                default_timeframe="1m",
                emit_tick_snapshots=config.emit_tick_snapshots,
            ),
        )

    event_journal = JsonlJournal(config.event_journal_path) if config.event_journal_path else None
    snapshot_journal = JsonlJournal(config.snapshot_journal_path) if config.snapshot_journal_path else None

    snapshots: list[FeatureSnapshot] = []
    for event in load_mt5pipe_events(config):
        if event_journal is not None:
            event_journal.append(event.to_record())
        event_snapshots = engine.on_event(event)
        snapshots.extend(event_snapshots)
        if snapshot_journal is not None:
            for snapshot in event_snapshots:
                snapshot_journal.append(snapshot.to_record())
    return snapshots


def _parse_date(value: str) -> dt.date:
    return dt.date.fromisoformat(value)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Replay MT5Pipe storage partitions through the Aphelion feature engine.")
    parser.add_argument("--mt5pipe-root", type=Path, required=True)
    parser.add_argument("--primary-symbol", default="XAUUSD")
    parser.add_argument("--start-date", type=_parse_date, required=True)
    parser.add_argument("--end-date", type=_parse_date, required=True)
    parser.add_argument("--tick-symbol", action="append", dest="tick_symbols")
    parser.add_argument("--bar-symbol", action="append", dest="bar_symbols")
    parser.add_argument("--bar-timeframe", action="append", dest="bar_timeframes")
    parser.add_argument("--storage-root", type=Path)
    parser.add_argument("--pipeline-config-path", type=Path)
    parser.add_argument("--event-journal-path", type=Path)
    parser.add_argument("--snapshot-journal-path", type=Path)
    parser.add_argument("--emit-tick-snapshots", action="store_true")
    parser.add_argument("--no-inferred-sessions", action="store_true")
    parser.add_argument("--include-btc", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    config = MT5PipeReplayConfig(
        mt5pipe_root=args.mt5pipe_root,
        primary_symbol=args.primary_symbol,
        start_date=args.start_date,
        end_date=args.end_date,
        tick_symbols=tuple(args.tick_symbols or [args.primary_symbol]),
        bar_symbols=tuple(args.bar_symbols or [args.primary_symbol]),
        bar_timeframes=tuple(args.bar_timeframes or ["M1", "M15", "H1"]),
        storage_root=args.storage_root,
        pipeline_config_path=args.pipeline_config_path,
        event_journal_path=args.event_journal_path,
        snapshot_journal_path=args.snapshot_journal_path,
        include_inferred_sessions=not args.no_inferred_sessions,
        emit_tick_snapshots=args.emit_tick_snapshots,
        include_btc=args.include_btc,
    )
    snapshots = replay_mt5pipe_into_engine(config)
    print(f"replayed_events={len(load_mt5pipe_events(config))}")
    print(f"emitted_snapshots={len(snapshots)}")
    if snapshots:
        print(f"latest_snapshot_ts_event_ns={snapshots[-1].ts_event_ns}")
        print(f"latest_snapshot_timeframe={snapshots[-1].timeframe}")
        print(f"latest_snapshot_missing_count={snapshots[-1].missing_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
