# Feature Engine Design

## 1. High-Level Architecture

The feature engine is designed for the journal-primary modular monolith described in the Aphelion architecture notes:

1. `MarketData -> journal.append(event)`
2. `EventBus -> FeatureEngine.on_event(event_from_journal)`
3. `FeatureEngine -> latest snapshot cache + journal-ready feature snapshot`
4. `Inference/Risk/OMS -> consume identical snapshot objects in live and replay`

The engine is:

- single-process on the hot path
- incremental and stateful
- deterministic for the same sequenced journal input
- point-in-time correct
- replay-safe with identical live and replay code paths

## 2. Project Structure

```text
src/aphelion/feature_engine/
  events.py
  engine.py
  observability.py
  policies.py
  registry.py
  replay.py
  snapshot.py
  state.py
  utils.py
  features/
    base.py
    microstructure.py
    market_structure.py
    volume_profile.py
    vwap.py
    technical.py
    cross_asset.py
    session_calendar.py
    regime.py
tests/
  test_feature_engine_unit.py
  test_feature_engine_properties.py
  test_replay_and_alignment.py
```

## 3. Event Model Definitions

The engine supports:

- `TickEvent`
- `BarCloseEvent`
- `SessionEvent`
- `NewsEvent`
- `CrossAssetBarEvent`
- internal `CrossAssetAlignedEvent`

All hot-path routing is keyed by journal sequence number and event timestamp.

## 4. Base Interfaces

Feature contracts are built around:

- `BaseFeature`
- `TickFeature`
- `BarFeature`
- `SessionFeature`
- `CrossAssetFeature`
- `RegimeFeature`

Each feature owns its own rolling state and exposes:

- `update(event, state, context)`
- `ready(state)`
- `value(state)`
- `reset(state, reason)`
- `serialize_state(state)`
- `restore_state(payload)`

## 5. Registry Design

`FeatureRegistry` owns registration, enable/disable, event-type routing, and aggregate version resolution. Cross-asset features also publish their required symbol dependencies to the engine.

## 6. State Store

`FeatureStateStore` keeps:

- per-feature state by `(feature, symbol, timeframe)`
- latest ticks
- latest bars
- session state
- active news context
- pending bar-close snapshots

The store exports and restores state for deterministic crash recovery.

## 7. Snapshot Schema

`FeatureSnapshot` is the canonical journalable output:

- `ts_event_ns`
- `symbol`
- `timeframe`
- `feature_version`
- `warmup_complete`
- `missing_count`
- `features`
- `metadata`

The snapshot is JSON-serializable and can be flattened for inference without changing the source object.

## 8. Engine Skeleton

`FeatureEngine`:

1. consumes journaled events
2. updates feature state incrementally
3. aligns cross-asset bars at the same logical timestamp
4. emits canonical snapshots for bar-close inference
5. exports/restores deterministic internal state

## 9. Representative Feature Coverage

Implemented category modules cover:

- microstructure and toxicity
- institutional market structure
- volume profile and delta
- session, anchored, and rolling VWAP
- classical technical indicators
- XAU cross-asset relationships
- session/calendar/news context
- regime state probabilities

Mathematically heavier models, such as Hawkes calibration and HMM emissions, are wired as production-ready skeletons with clear calibration seams rather than toy placeholders.

## 10. Replay Design

`replay_from_journal()` iterates historical journal records, reconstructs typed events, and feeds them through `FeatureEngine.on_event()` exactly as live dispatch does.

## 11. Tests

The test suite covers:

- feature-level units
- randomized property checks
- replay determinism
- missing-data behavior
- warmup gating
- cross-asset alignment
- session reset behavior

## 12. Extension Roadmap

Recommended next steps:

1. swap in production journal codecs and schema registry
2. calibrate Hawkes, VPIN bucket sizing, and HMM emission parameters from historical XAUUSD data
3. add broker/session calendars and venue-specific holiday handling
4. persist snapshots to a research lake for offline model iteration
5. migrate the heaviest statistical kernels to Rust or Cython if latency budgets demand it

