# GIGA-NI Feature Consolidation Report

Date: 2026-04-20
Workspace audited: `C:\Aphelion\_extracted\giga-ni\GIGA-NI-main`

## Scope

This audit covered the legacy compatibility pack under `aphelion/features/` and the canonical event-driven stack under `aphelion/feature_engine/`.

Two important notes:

1. The repo state I consolidated already had thin shims in `aphelion/features/` rather than the original full legacy implementations.
2. The original batch-style implementations were migrated into a new canonical namespace, `aphelion/feature_engine/legacy/`, so the logic now lives under `feature_engine` while legacy import paths continue to work.

## Legacy Features Audit

Pre-consolidation inventory of `aphelion/features/*.py`:

| File | LOC | External Imports | Status |
| --- | ---: | ---: | --- |
| `__init__.py` | 11 | 0 | KEEP: package/deprecation shim |
| `cointegration.py` | 3 | 1 | LIVE/UNIQUE |
| `cross_impact.py` | 3 | 1 | LIVE/UNIQUE |
| `engine.py` | 11 | 4 | LIVE/DUP |
| `halftrend.py` | 3 | 0 | DEAD wrapper |
| `market_structure.py` | 3 | 2 | LIVE/DUP |
| `microstructure.py` | 3 | 7 | LIVE/DUP |
| `mtf.py` | 3 | 1 | LIVE/UNIQUE |
| `registry.py` | 3 | 0 | DEAD wrapper |
| `sessions.py` | 3 | 0 | DEAD wrapper |
| `signature.py` | 3 | 1 | LIVE/UNIQUE |
| `volume_profile.py` | 3 | 1 | LIVE/DUP |
| `vwap.py` | 3 | 1 | LIVE/DUP |

External-import detail:

- `cointegration.py`: `tests/features/test_cointegration.py`
- `cross_impact.py`: `tests/features/test_signature_cross_impact.py`
- `engine.py`: `tests/features/test_engine.py`, `tests/features/test_engine_v2.py`, `tests/features/test_signature_cross_impact.py`, `tests/integration/test_pipeline.py`
- `market_structure.py`: `tests/features/test_market_structure.py`, `tests/features/test_market_structure_v2.py`
- `microstructure.py`: `tests/core/test_improvements.py`, `tests/features/test_advanced_models.py`, `tests/features/test_microstructure.py`, `tests/features/test_microstructure_v2.py`
- `mtf.py`: `tests/features/test_mtf.py`
- `signature.py`: `tests/features/test_signature_cross_impact.py`
- `volume_profile.py`: `tests/features/test_volume_profile.py`
- `vwap.py`: `tests/features/test_vwap.py`

Dead-wrapper deletions:

- Deleted `aphelion/features/halftrend.py`
- Deleted `aphelion/features/registry.py`
- Deleted `aphelion/features/sessions.py`
- Total wrapper lines removed from `aphelion/features/`: 9
- Dangling imports introduced: 0

## Feature Engine Inventory

Pre-consolidation `aphelion/feature_engine/` inventory contained 31 Python files:

```text
__init__.py                               71
defaults.py                               43
engine.py                                296
events.py                                 93
feature_snapshot.py                        8
features/__init__.py                      19
features/_microstructure_impl.py         651
features/base.py                         123
features/cross_asset.py                  151
features/market_structure.py             227
features/microstructure.py               339
features/regime.py                       165
features/session_calendar.py             127
features/technical.py                    356
features/volume_profile.py               146
features/vwap.py                         111
integrations/__init__.py                   2
integrations/mt5pipe.py                  404
journal.py                                18
legacy_runtime.py                        143
microstructure_feature.py                  3
observability.py                          46
policies.py                               55
regime_state_feature.py                    3
registry.py                               48
replay.py                                 36
snapshot.py                               83
state.py                                 124
technical_feature.py                       3
tick_event.py                              4
utils.py                                 168
```

Post-consolidation, `aphelion/feature_engine/` now contains 44 Python files because the legacy logic has been migrated into `aphelion/feature_engine/legacy/`.

Migrated legacy package inventory:

```text
legacy/__init__.py                        20
legacy/cointegration.py                  260
legacy/cross_impact.py                   177
legacy/engine.py                         811
legacy/halftrend.py                      105
legacy/market_structure.py               385
legacy/microstructure.py                 836
legacy/mtf.py                            102
legacy/registry.py                       152
legacy/sessions.py                        23
legacy/signature.py                      128
legacy/volume_profile.py                 336
legacy/vwap.py                           130
```

## Duplication and Authority Matrix

| Legacy File | Status | Action | Target Location |
| --- | --- | --- | --- |
| `__init__.py` | compat package | kept as deprecated namespace shim | `aphelion/features/__init__.py` |
| `cointegration.py` | live / unique with partial overlap to `features/cross_asset.py` | ported legacy engine into canonical namespace | `aphelion/feature_engine/legacy/cointegration.py` |
| `cross_impact.py` | live / unique | ported | `aphelion/feature_engine/legacy/cross_impact.py` |
| `engine.py` | live / duplicated surface | repointed shim to canonical legacy package | `aphelion/feature_engine/legacy/engine.py` |
| `halftrend.py` | dead wrapper | deleted wrapper, preserved underlying dependency for legacy engine | `aphelion/feature_engine/legacy/halftrend.py` |
| `market_structure.py` | duplicate concept | event-driven `features/market_structure.py` is authority; batch API preserved | `aphelion/feature_engine/legacy/market_structure.py` |
| `microstructure.py` | duplicate concept | event-driven `_microstructure_impl.py` / `features/microstructure.py` are authority; batch API preserved | `aphelion/feature_engine/legacy/microstructure.py` |
| `mtf.py` | live / unique | ported | `aphelion/feature_engine/legacy/mtf.py` |
| `registry.py` | dead wrapper | deleted wrapper, preserved legacy helper for migrated batch engine | `aphelion/feature_engine/legacy/registry.py` |
| `sessions.py` | dead wrapper | deleted wrapper, preserved legacy helper for migrated batch engine | `aphelion/feature_engine/legacy/sessions.py` |
| `signature.py` | live / unique | ported | `aphelion/feature_engine/legacy/signature.py` |
| `volume_profile.py` | duplicate concept | event-driven `features/volume_profile.py` is authority; batch API preserved | `aphelion/feature_engine/legacy/volume_profile.py` |
| `vwap.py` | duplicate concept | event-driven `features/vwap.py` is authority; batch API preserved | `aphelion/feature_engine/legacy/vwap.py` |

## Import Migration Log

No repo-wide source import rewrites were required.

Compatibility strategy:

- Legacy module imports such as `from aphelion.features.microstructure import MicrostructureEngine` continue to work through the existing wrappers.
- `from aphelion.features.engine import FeatureEngine` now resolves to `aphelion.feature_engine.legacy.engine.FeatureEngine`.
- Runtime backtest/paper code continues to use `aphelion.feature_engine.legacy_runtime.LegacyFeatureEngine`, so the event-driven backtest path was left untouched.

Dead-wrapper import impact:

- `aphelion.features.halftrend`: no external imports found
- `aphelion.features.registry`: no external imports found
- `aphelion.features.sessions`: no external imports found

## Files Changed

Compatibility package changes:

- Updated `aphelion/features/__init__.py` to act as a deprecated namespace shim
- Updated `aphelion/features/engine.py` to point at `aphelion.feature_engine.legacy.engine.FeatureEngine`
- Kept live wrappers for:
  - `cointegration.py`
  - `cross_impact.py`
  - `market_structure.py`
  - `microstructure.py`
  - `mtf.py`
  - `signature.py`
  - `volume_profile.py`
  - `vwap.py`

Canonical ownership changes:

- Added `aphelion/feature_engine/legacy/` with 13 migrated modules

Deleted wrappers:

- `aphelion/features/halftrend.py`
- `aphelion/features/registry.py`
- `aphelion/features/sessions.py`

## Validation

### Legacy/API Validation

Command:

```text
python -m pytest --noconftest tests/features/test_cointegration.py tests/features/test_microstructure.py tests/features/test_microstructure_v2.py tests/features/test_advanced_models.py tests/features/test_market_structure.py tests/features/test_market_structure_v2.py tests/features/test_volume_profile.py tests/features/test_vwap.py tests/features/test_mtf.py tests/features/test_engine.py tests/features/test_engine_v2.py tests/features/test_signature_cross_impact.py tests/integration/test_pipeline.py -q
```

Result:

- 103/103 passed

### Feature Engine Validation

Command:

```text
python -m pytest --noconftest tests/test_feature_engine_unit.py tests/test_feature_engine_properties.py tests/test_replay_and_alignment.py tests/test_inference_feature_schema.py tests/test_task_01_bar_snapshot_wire.py tests/test_task_02_vpin_autosizing.py tests/test_task_03_ofi_normalization.py tests/test_task_04_gk_vol.py tests/test_task_05_yz_vol.py tests/test_task_06_parkinson_vol.py tests/test_task_07_vrp.py tests/test_task_08_hurst.py tests/test_task_09_fractal_dimension.py tests/test_task_10_tick_runs.py tests/test_task_11_bounce_rate.py tests/test_task_12_quote_stuffing.py tests/test_task_13_hawkes_imbalance.py tests/test_task_14_microstructure_ready.py tests/test_mt5pipe_integration.py -q
```

Result:

- 51/51 passed

### Backtest Validation

Command:

```text
python -m pytest --noconftest tests/backtest -q
```

Result:

- 195/195 passed

Runtime smoke:

```text
python -m aphelion config validate --config config/backtest.yaml
python -m aphelion backtest --config config/backtest.yaml
```

Outcome:

- Config validated successfully
- Backtest command completed without crashing
- Local dataset availability produced `0` processed events, so there is no meaningful PnL/trade-count regression number to compare in this workspace

### Inference Latency Smoke

Measured on `aphelion.feature_engine.legacy_runtime.LegacyFeatureEngine` over a synthetic 6,000-tick stream with 99 emitted M1 snapshots:

- Average latency: `1.107 ms/snapshot`
- P95 latency: `1.365 ms/snapshot`
- Max latency: `6.111 ms`
- Average feature width: `170.4` keys
- Last snapshot width: `171` keys

This is comfortably below the `<50 ms/snapshot` budget from the request.

### Type Coverage

`pyright` is not installed in this environment, so I could not produce `feature_engine_types.json`.

Fallback AST-based coverage estimate across `aphelion/feature_engine/**/*.py`:

- Functions scanned: `416`
- Fully annotated functions: `383`
- Estimated coverage: `92.1%`

This clears the requested `>=85%` threshold.

## Final State

- `aphelion/features/` remains as a deprecated compatibility package
- Dead wrappers removed: `3`
- Live legacy APIs now owned by `aphelion/feature_engine/legacy/`
- Canonical event-driven runtime remains under `aphelion/feature_engine/`
- Backtest-facing runtime path (`legacy_runtime`) still works
- Legacy feature tests, feature-engine tests, and backtest tests all pass

## Follow-Ups

1. If full PnL regression numbers are required, mount a real MT5/backtest dataset and rerun `python -m aphelion backtest --config config/backtest.yaml`.
2. If strict static typing artifacts are required, install `pyright` in the workspace and rerun the requested JSON export.
