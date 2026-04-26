# `aphelion_data.py` Audit And Migration

## Summary

`aphelion_data.py` was a legacy orchestration script that bundled terminal UX, MT5 ingestion, feature engineering, dataset packaging, and HYDRA training into one file.

- File size audited: 1,474 LOC in this snapshot
- Direct Python imports found: 1
- Non-import string references found: 2
- Conclusion: not a 100% duplicate of `mt5pipe`

The MT5 ingestion, merge, state/feature compilation, cataloging, and quality-validation responsibilities now belong in `mt5pipe`. The remaining unique logic is the gold-specific feature pack plus a few legacy CLI/dataset convenience wrappers.

## Major Sections

1. Terminal UX and ad-hoc logging
   - ANSI color helpers, banners, progress bars, file-save summaries.
   - No `mt5pipe` equivalent; obsolete once the script is removed.
2. File/config helpers
   - Path helpers, CSV/JSON save helpers, rolling helpers, legacy CSV loading.
   - Mostly superseded by `mt5pipe.storage`, `mt5pipe.catalog`, and standard library utilities.
3. Gold-specific feature pack
   - `feat_asian_range`, previous-session levels, liquidity sweeps, DXY/silver relationships, spread anomalies, MTF confluence, macro timing, plus the extended pack imported from `aphelion.gold_feature_pack_extra`.
   - This is unique logic and was extracted to `aphelion.gold_feature_pack`.
4. MT5 ingestion phase
   - MT5 import/bootstrap, bar fetching, tick fetching, data enrichment, resume handling.
   - Replaced by `mt5pipe.mt5.connection`, `mt5pipe.ingestion`, `mt5pipe.backfill`, and `mt5pipe.bars`.
5. Feature-build phase
   - Builds a large Pandas feature table and writes a parquet.
   - Superseded by `mt5pipe.features` + `mt5pipe.compiler`.
6. Dataset-prep phase
   - Splits train/val/test, scales features, packages `.npz` files, writes scaler/meta JSON.
   - Partially duplicated by `mt5pipe.features.dataset`, `mt5pipe.compiler.DatasetCompiler`, and `mt5pipe.compiler.training`.
7. Training phase / CLI main
   - Legacy wrapper around HYDRA training and a monolithic command-line entrypoint.
   - Replaced by `scripts/train_hydra.py`, `mt5pipe.cli`, and package entrypoints.

## Definitions

### Classes

| Symbol | Lines | Purpose | Status |
| --- | ---: | --- | --- |
| `C` | 53-70 | ANSI terminal color constants | Delete |
| `Stats` | 194-221 | Session counters / summary printing | Delete |

### Functions

| Symbol | Lines | Purpose | Replacement |
| --- | ---: | --- | --- |
| `supports_color` | 72-73 | TTY color detection | Delete |
| `c` | 77-78 | Color formatting helper | Delete |
| `_elapsed` | 89-91 | Elapsed-time formatter | Delete |
| `log` | 93-119 | Ad-hoc terminal/file logger | `mt5pipe.utils.logging` / structlog |
| `section` | 121-129 | Section banner printer | Delete |
| `banner` | 131-139 | Startup banner printer | Delete |
| `progress_bar` | 141-146 | Terminal progress rendering | Delete |
| `save_msg` | 148-150 | Save summary printer | Delete |
| `get_data_dirs` | 159-165 | Legacy raw/processed path setup | `mt5pipe.storage.paths.StoragePaths` |
| `save_csv` | 229-234 | CSV writer wrapper | standard library / pandas |
| `save_json` | 236-240 | JSON writer wrapper | standard library |
| `skip` | 242-246 | Resume helper | `mt5pipe.storage.checkpoint_db.CheckpointDB` / caller logic |
| `ema` | 248-251 | Simple EMA helper | `mt5pipe.features.internal.statistics` (closest) |
| `rolling_mean` | 253-257 | Rolling mean helper | `mt5pipe.features.internal.statistics` / pandas |
| `rolling_std` | 259-262 | Rolling std helper | `mt5pipe.features.internal.statistics` / pandas |
| `resolve_existing_symbol_raw_file` | 264-269 | Legacy CSV lookup | `mt5pipe.storage.paths` |
| `load_tf` | 271-276 | Legacy timeframe CSV loader | `mt5pipe.storage.parquet_store.ParquetStore` |
| `feat_asian_range` | 278-307 | Asian-session range features | moved to `aphelion.gold_feature_pack` |
| `feat_previous_levels` | 309-363 | Prior day/week/month levels | moved to `aphelion.gold_feature_pack` |
| `feat_liquidity_sweeps` | 365-393 | Stop-hunt / liquidity sweep flags | moved to `aphelion.gold_feature_pack` |
| `feat_dxy_beta` | 395-419 | Rolling gold-vs-DXY beta/corr | moved to `aphelion.gold_feature_pack` |
| `feat_order_blocks` | 421-464 | Simple order-block heuristics | moved to `aphelion.gold_feature_pack` |
| `feat_displacement` | 466-504 | Displacement/ATR impulse features | moved to `aphelion.gold_feature_pack` |
| `feat_silver_relationship` | 506-534 | Gold/silver relationship features | moved to `aphelion.gold_feature_pack` |
| `feat_spread_anomaly` | 536-559 | Spread anomaly detection | moved to `aphelion.gold_feature_pack` |
| `feat_mtf_confluence` | 561-597 | Multi-timeframe confluence score | moved to `aphelion.gold_feature_pack` |
| `feat_macro_timing` | 599-629 | NFP/CPI/Fed timing flags | moved to `aphelion.gold_feature_pack` |
| `add_high_value_gold_features` | 631-645 | Gold feature-pack orchestrator | moved to `aphelion.gold_feature_pack` |
| `init_mt5` | 653-659 | Import/guard MT5 | `mt5pipe.mt5.connection.MT5Connection` |
| `connect_mt5` | 661-678 | MT5 login/init sequence | `mt5pipe.mt5.connection.MT5Connection` |
| `probe_earliest` | 680-682 | Earliest available-bar probe | `mt5pipe.backfill.engine.BackfillEngine` |
| `fetch_bars` | 684-714 | Pull and persist OHLCV bars | `mt5pipe.ingestion.bars.fetch_bars_chunk`, `store_bars_by_date` |
| `enrich_ohlcv` | 716-724 | Derived spread/body columns | `mt5pipe.features.public` / compiler feature builders |
| `fetch_phase` | 726-820 | Full MT5 download orchestration | `mt5pipe.backfill`, `mt5pipe.ingestion`, `mt5pipe.bars` |
| `_fetch_ticks` | 822-912 | Tick backfill and persistence | `mt5pipe.ingestion.ticks`, `mt5pipe.quality.cleaning`, `mt5pipe.backfill.sync` |
| `_build_enriched_m1` | 914-967 | Merge M1 + context symbols | `mt5pipe.state.service.StateService` / compiler state inputs |
| `build_features_phase` | 975-1238 | Full Pandas feature pipeline | `mt5pipe.features.FeatureService`, `mt5pipe.compiler.DatasetCompiler` |
| `prepare_dataset_phase` | 1247-1542 | Train/val/test packaging + scaler | `mt5pipe.features.dataset`, `mt5pipe.compiler.DatasetCompiler`, `mt5pipe.compiler.training` |
| `train_phase` | 1551-1584 | Legacy HYDRA training wrapper | `scripts/train_hydra.py`, `mt5pipe.compiler.training.ExperimentRunner` |
| `main` | 1590-1672 | Monolithic CLI | `mt5pipe.cli.app`, package entrypoints |

## Cross-Reference To `mt5pipe`

| `aphelion_data.py` | `mt5pipe` equivalent | Match? | Notes |
| --- | --- | --- | --- |
| `init_mt5` / `connect_mt5` | `mt5pipe.mt5.connection.MT5Connection` | Partial | Same responsibility, cleaner API |
| `probe_earliest` / `fetch_phase` | `mt5pipe.backfill.engine.BackfillEngine` | Partial | Backfill orchestration moved out of script |
| `fetch_bars` | `mt5pipe.ingestion.bars.fetch_bars_chunk` + `store_bars_by_date` | Yes | API split into fetch/store functions |
| `_fetch_ticks` | `mt5pipe.ingestion.ticks.fetch_ticks_chunk` + `store_ticks_by_date` | Yes | Dedup/cleaning also in `mt5pipe.quality.cleaning` |
| raw multi-broker sync in `_fetch_ticks` | `mt5pipe.backfill.sync.run_synchronized_tick_backfill` | Yes | Dedicated synchronized backfill path |
| raw merge assumptions in feature build | `mt5pipe.merge.canonical.merge_canonical_ticks` | Yes | Canonical merge extracted and QA’d |
| feature generation in `build_features_phase` | `mt5pipe.features.FeatureService` | Partial | Service replaces bulk Pandas script flow |
| label generation in `build_features_phase` | `mt5pipe.labels.LabelService` | Yes | Label packs are package-owned |
| dataset publish/manifest behavior | `mt5pipe.compiler.DatasetCompiler` | Yes | Compiler owns registry + manifests |
| dataset metadata registry | `mt5pipe.catalog.CatalogDB` | Yes | Catalog sector owns lineage/metadata |
| quality validation / report logic | `mt5pipe.quality.cleaning`, `merge_qa`, `report` | Yes | Quality checks now package-owned |
| train/experiment orchestration | `mt5pipe.compiler.training.ExperimentRunner` | Partial | Legacy script still wrapped local HYDRA trainer |

## Unique Logic Flagged For Porting

The file was **not** a pure duplicate. The following spans were unique or materially different and would have been lost by a straight delete:

| Legacy span | Approx. size | Action taken |
| --- | ---: | --- |
| Gold feature pack (`feat_asian_range` through `add_high_value_gold_features`) | ~368 LOC | moved to `aphelion.gold_feature_pack` |
| ANSI UI / ad-hoc logger / progress output | ~98 LOC | removed instead of ported |
| Dataset `.npz` packaging convenience layer | ~296 LOC | deprecated; modern flow is `mt5pipe` compiler + trainer |
| Legacy training/main wrappers | ~117 LOC | deprecated; use package scripts/CLIs |

## Import Audit

Direct imports found before migration:

| File | Line | Usage | Migration |
| --- | ---: | --- | --- |
| `tests/intelligence/test_gold_feature_pack.py` | 10 | `from aphelion_data import add_high_value_gold_features, feat_asian_range` | Updated to `from aphelion.gold_feature_pack import ...` |

String/documentation references updated:

| File | Line | Old text | New text |
| --- | ---: | --- | --- |
| `aphelion/paper/launchers.py` | 269 | told users to run `aphelion_data.py` | now points to `mt5pipe` / prepared datasets |
| `scripts/train_hydra.py` | 47 | referred to bulk downloader in `aphelion_data.py` | now refers to `mt5pipe` dataset preparation |

## Removal Decision

`aphelion_data.py` should not remain in active use.

- Legacy implementation archived to `_archive/deprecated/aphelion_data.py.bak`
- Active path replaced with a deprecation stub that raises immediately
- Imports migrated off the file
- Gold-only reusable logic preserved in `aphelion.gold_feature_pack`
