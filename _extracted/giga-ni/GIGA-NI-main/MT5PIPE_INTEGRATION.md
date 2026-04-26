# MT5Pipe Integration

The feature engine can replay MT5Pipe storage partitions directly.

## What It Reads

- canonical ticks from `canonical_ticks/symbol=<SYMBOL>/date=<YYYY-MM-DD>/part-*.parquet`
- built bars from `bars/symbol=<SYMBOL>/timeframe=<TF>/date=<YYYY-MM-DD>/part-*.parquet`
- storage root from `config/pipeline.yaml` unless overridden

## What It Emits

- deterministic `TickEvent`, `BarCloseEvent`, `CrossAssetBarEvent`, and inferred `SessionEvent`
- canonical `FeatureSnapshot` objects through the same live/replay engine path
- optional append-only JSONL journals for both source events and emitted feature snapshots

## Example

Run directly from source:

```powershell
$env:PYTHONPATH="C:\Users\poyan\OneDrive\Desktop\Aphelion\src"
python -m aphelion.feature_engine.integrations.mt5pipe `
  --mt5pipe-root "C:\Users\poyan\OneDrive\Desktop\Aphelion\DataPipeline" `
  --start-date 2026-01-01 `
  --end-date 2026-01-31 `
  --tick-symbol XAUUSD `
  --bar-symbol XAUUSD `
  --bar-symbol DXY `
  --bar-timeframe M1 `
  --bar-timeframe M15 `
  --bar-timeframe H1 `
  --event-journal-path "C:\Users\poyan\OneDrive\Desktop\Aphelion\out\events.jsonl" `
  --snapshot-journal-path "C:\Users\poyan\OneDrive\Desktop\Aphelion\out\feature_snapshots.jsonl"
```

## Notes

- MT5Pipe bar timestamps are bar-open timestamps; the adapter converts them to bar-close event times before feeding the engine.
- Cross-asset features are enabled only when non-primary bar symbols are included in the replay input.
- If the MT5Pipe storage root is empty, the command exits cleanly with `replayed_events=0` and `emitted_snapshots=0`.

