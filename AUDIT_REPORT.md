# APHELION RESEARCH — CODEBASE AUDIT

**Generated:** 2026-04-20
**Scope:** 7 zips at `C:\aphelion\` → 6 unique repos (GIGA-NI (3).zip == GIGA-NI (4).zip byte-identical)
**Extract root:** `C:\aphelion\_extracted\`

---

## EXECUTIVE SUMMARY

| Metric | Value |
|---|---|
| Zips delivered | 7 (1 pure dup) |
| Unique repos | 6 |
| Total Python LOC | 241,510 |
| Total C++/H LOC | 10,934 |
| Total test files | 325 (dedupe-less) |
| Canonical repo | **giga-ni** (unified root, 105,564 py LOC, 154 tests) |
| CI/CD configured | **None** (zero `.github/workflows` anywhere) |
| Type hint coverage (giga-ni) | 48 % |
| Logger : print ratio (giga-ni) | 315 : 90 ≈ 3.5 : 1 |
| Bare `except:` clauses | 0 (clean) |
| TODO/FIXME markers | 5 (low) |
| Hardcoded secrets | 0 |
| Broken imports (giga-ni) | **11** (`machinelearning.models.*`) |

**One-line verdict:** GIGA-NI is the intended unified repo and ~80 % real quant-research code, but the final merge dropped `machinelearning/models/` and left two parallel feature systems, breaking inference/training paths. Predecessor repos are now stale snapshots.

---

## SECTION A — INVENTORY

### A.1 Archive inventory

| File | Size | SHA256 (head) | Verdict |
|---|---|---|---|
| Aphelion-Reasearch-main.zip | 2.12 MB | 9db3a220… | legacy, 87 % absorbed into giga-ni |
| Aphelion-nueral-main.zip | 703 KB | c1941824… | legacy, 67 % absorbed (DROPPED models/) |
| DataPipeline-main.zip | 324 KB | eec3d4b3… | legacy, 81 % absorbed |
| Future-engine-main.zip | 76 KB | 807519a7… | legacy, 92 % absorbed |
| GIGA-NI-main (3).zip | 1.17 MB | 87358431… | **CANONICAL** |
| GIGA-NI-main (4).zip | 1.17 MB | 87358431… | **BYTE-IDENTICAL DUP of (3)** |
| cpp-cooker-main.zip | 127 KB | 08fb073f… | separate C++ sim engine (v1.0.0) |

### A.2 Per-repo size

| Repo | .py files | Py LOC | Tests | Key subtree |
|---|---|---|---|---|
| aphelion-research | 366 | 68,208 | 98 | `aphelion/` 20-module research stack |
| aphelion-neural | 188 | 34,646 | 31 | `APH/`, `data/mt5pipe/`, `machinelearning/` |
| datapipeline | 147 | 27,578 | 23 | `mt5pipe/` MT5 ingestion + compiler |
| future-engine | 55 | 5,514 | 19 | `src/aphelion/feature_engine` + `inference` |
| **giga-ni** | **618** | **105,564** | **154** | **aphelion + mt5pipe + machinelearning** |
| cpp-cooker | 42 (.cpp+.h) | 10,934 | — | historical sim engine (QuantLib) |

### A.3 giga-ni module breakdown (aphelion/ subtree, 2.2 MB)

```
aphelion/
├── app.py, __main__.py          # canonical entry (EventDrivenSuperSystem)
├── core/                        # event_bus, clock, config, data_layer, registry
├── feature_engine/  (31 py)     # NEW event-driven journal-based engine
├── features/        (13 py)     # LEGACY feature pack (partial dead code)
├── inference/       (3  py)     # 107-D schema contract
├── integrations/supersystem/    # 5 bridges (event, feature, signal, execution, super_pipeline)
├── intelligence/
│   ├── hydra/       (16 py)     # TFT, LSTM, CNN, TCN, MoE, XGB, Transformer ensemble
│   ├── echo/, forge/, kronos/, rl_exit/, shadow/
├── evolution/                   # zeus, cipher, meridian, prometheus, auto_optimizer
├── governance/
│   ├── council/                 # sola, veto, edge_decay, improvement_loop, regime_awareness
│   └── olympus/                 # allocator, monitor, orchestrator, reporter
├── risk/
│   ├── sentinel/                # v2, monitor, sizer, circuit_breaker, validator
│   ├── titan/                   # gate + 5 validators (stability, stress, performance, regression, latency)
│   └── execution/               # almgren_chriss
├── nemesis/                     # chronos, leviathan, pandora, verdict, contrarian, stress_monitor
├── macro/                       # argus, atlas, herald, nexus, oracle
├── flow/                        # phantom, specter
├── hephaestus/     (17 py)      # LLM code-gen agent (codegen, sandbox, deployer, pine_script)
├── ares/                        # order coordinator
├── backtest/       (9  py)      # event-driven, walk-forward, monte_carlo
├── paper/          (7  py)      # paper trading runner/ledger/feed
├── money/, filters/, aphelion_model/
└── tui/            (38 py)      # Textual TUI w/ 18 screens, 10 widgets
```

---

## SECTION B — DUPLICATES REPORT

### B.1 Exact duplicates (SHA256-identical)

**Archive level:** `GIGA-NI-main (3).zip` == `GIGA-NI-main (4).zip` → delete one.

**File level — 507 dup-hash groups across repos** (includes 69 empty `__init__.py`).

### B.2 Cross-repo absorption into giga-ni (unique-hash basis)

| Source repo | Unique hashes absorbed | Total unique | % absorbed | Files NOT in giga-ni |
|---|---|---|---|---|
| aphelion-research | 306 | 351 | **87 %** | 45 (all drifted versions of files present in giga-ni) |
| aphelion-neural | 119 | 176 | **67 %** | 57 (includes `machinelearning/models/*` — **CRITICAL**) |
| datapipeline | 110 | 135 | **81 %** | 25 (mt5pipe drift + tests) |
| future-engine | 51 | 55 | **92 %** | 4 (init files only) |

**Implication:** Old-repo unabsorbed files are almost all *stale edits* of files re-merged into giga-ni, EXCEPT `aphelion-neural/machinelearning/models/` which was genuinely dropped.

### B.3 Intra-giga-ni redundancy

1. **Parallel feature systems** — `aphelion/features/` (13 py, legacy, 0 full-package imports but some submodule refs still live) AND `aphelion/feature_engine/` (31 py, new, 69 imports). `FEATURE_ENGINE_DESIGN.md` documents `feature_engine` as canonical. Dead modules in `features/`: `halftrend.py`, `registry.py`, `sessions.py` (0 inbound refs).
2. **Monolithic orchestrator** — `aphelion_data.py` (1,676 LOC, 84 KB) replicates the full fetch → features → HYDRA train flow in one script; overlaps with `mt5pipe.tools.super_pipeline_tui` + `machinelearning.training.train` + `aphelion.__main__`.
3. **Entry-point shims** — `aphelion.py`, `run_paper.py`, `runall.py` self-label as legacy compat shims (TODO: remove after install scripts adopt).
4. **Dev utilities in repo root** — `map.py` (project mapper), `sxcas.py` (process scanner misnamed); should live in `scripts/` or separate dev-tools repo.
5. **`codex_temp/`** — 48 KB of hash-named scratch files from codex CLI; drop wholesale.
6. **`config/legacy-packaging/`** — archived packaging snapshots from old repos; purgeable once confirmed.

### B.4 Cross-repo mt5pipe triplication

`mt5pipe/` exists in THREE places:
- `datapipeline/DataPipeline-main/mt5pipe/` (147 py)
- `aphelion-neural/Aphelion-nueral-main/data/mt5pipe/` (embedded dup)
- `giga-ni/GIGA-NI-main/mt5pipe/` (canonical)

Plus drifted versions in each. All older copies should be deleted.

---

## SECTION C — LEGITIMACY SCORECARD

| Component (giga-ni) | Type | Real/Proto | Tests? | Docs? | Logs? | Errors? | Maturity | Red flags |
|---|---|---|---|---|---|---|---|---|
| `mt5pipe/` (ingestion+compiler) | Infra | Real | ~30 tests | MT5PIPE_INTEGRATION.md, strong README | Yes (structlog) | Partial | **80 %** | MT5 Windows-only |
| `aphelion/feature_engine/` | Alpha | Real | dedicated dir | FEATURE_ENGINE_DESIGN.md | Yes | Yes | **75 %** | Legacy features/ still present |
| `aphelion/features/` (legacy) | Alpha | **Stale** | partial | none | Mixed | Mixed | **35 %** | 3 dead modules, replaced by feature_engine |
| `aphelion/inference/` | Infra | Real | yes | INFERENCE_HANDOFF.md | Yes | Yes | **70 %** | 107-D contract stable |
| `aphelion/intelligence/hydra/` (ensemble) | Alpha | Real | `tests/intelligence/*` | partial | Yes | Yes | **65 %** | 16 model files, no perf bench in repo |
| `machinelearning/` (training path) | Alpha | **Broken** | 7 test files | none | Yes | — | **30 %** | **Missing `models/` dir → 11 import errors** |
| `aphelion/integrations/supersystem/` | Infra | Real | integration tests | supersystem README fragments | Yes | Yes | **70 %** | `signal_bridge.py` broken via ML models gap |
| `aphelion/risk/sentinel/` | Risk | Real | yes | partial | Yes | Yes | **75 %** | circuit_breaker + validator present |
| `aphelion/risk/titan/` | Risk | Real | yes (5 validators) | partial | Yes | Yes | **70 %** | gate + regression/stress/latency/performance/stability |
| `aphelion/governance/olympus/` | Gov | Real | yes | partial | Yes | Yes | **60 %** | orchestrator+allocator+monitor+reporter |
| `aphelion/governance/council/` | Gov | Real | yes | partial | Yes | Yes | **55 %** | sola, veto, edge_decay, regime_awareness |
| `aphelion/nemesis/` | Gov | Real | yes | partial | Yes | Yes | **50 %** | chronos/leviathan/pandora/verdict — many "gods" |
| `aphelion/evolution/` (zeus/cipher/meridian/prometheus) | Alpha | Real | yes | partial | Yes | Yes | **55 %** | overlap between evolution variants? untested |
| `aphelion/hephaestus/` (LLM codegen) | Aux | Prototype | yes (llm_client) | partial | Yes | Yes | **50 %** | production LLM cost/latency unvalidated |
| `aphelion/backtest/` | BT | Real | yes | partial | Yes | Yes | **70 %** | walk_forward, monte_carlo, analytics |
| `aphelion/paper/` | Exec | Real | yes | partial | Yes | Yes | **65 %** | launcher, feed, ledger, session, readiness |
| `aphelion/tui/` | UI | Real | yes (`tests/tui/`) | screens documented | — | Yes | **70 %** | Textual-based, 18 screens |
| `aphelion/ares/` (order coord) | Exec | Real | yes | prompts dir | Yes | Yes | **55 %** | coordinator + journal |
| `aphelion/macro/` (argus/atlas/herald/nexus/oracle) | Aux | Real | partial | — | Yes | Yes | **45 %** | 5 macro submodules, unclear lineage |
| `aphelion_data.py` (monolith) | Orchestration | **Dup** | none | inline | Mixed (prints) | partial | **40 %** | 1,676 LOC single file; redundant with modular pipeline |
| `cpp-cooker/` (sim engine) | Infra | Real | none | strong README | Yes (std::cout?) | unknown | **50 %** | 10,934 LOC, 0 test infra visible; QuantLib dep via vcpkg |

**Aggregate maturity (LOC-weighted over giga-ni):** ≈ **62 %**.

### C.1 Red flags ranked

1. 🔴 **Missing `machinelearning/models/` in giga-ni** — breaks `training/train.py`, `training/module.py`, `regime/moe.py`, `signal/publisher.py`, `integrations/supersystem/signal_bridge.py`, 6 tests. Production ML→signal bridge cannot import. Fix: port `aphelion-neural/Aphelion-nueral-main/machinelearning/models/{__init__,base,blocks,tft,ablation,interpret}.py`.
2. 🔴 **No CI/CD** — 0 `.github/workflows/*.yml` in any repo. Test suite exists (154 files in giga-ni) but never gated.
3. 🟡 **Parallel feature systems** — `features/` + `feature_engine/` coexist; dead modules in legacy pack (`halftrend`, `registry`, `sessions`).
4. 🟡 **1,676-LOC monolith** (`aphelion_data.py`) duplicates modular pipeline.
5. 🟡 **48 % type-hint coverage** — half of `def` signatures lack return annotations.
6. 🟡 **90 `print(` calls** in production paths — should be structlog.
7. 🟡 **Dev tools in repo root** (`map.py`, `sxcas.py`) pollute entry-point namespace.
8. 🟡 **`codex_temp/`** — 48 KB of agent scratch files committed.
9. 🟡 **Single asset** — XAU/USD only. No portfolio correlation logic surfaced.
10. 🟡 **No cost/slippage model visibility** — almgren_chriss present but no verified fill-quality harness.
11. 🟢 **Low TODO count (5)** — either clean or tracked externally (verify).
12. 🟢 **Zero bare-except** — good defensive hygiene.
13. 🟢 **Zero hardcoded credentials** — `.env.example` only.
14. 🟢 **Strong governance layer** — council/olympus/nemesis/titan overlays show serious risk thinking.

---

## SECTION D — ARCHITECTURE & DATA FLOW

### D.1 Canonical runtime path (giga-ni)

```
┌────────────────────┐
│ MT5 terminal(s)    │  Windows, dual-broker
└─────────┬──────────┘
          │ MetaTrader5 API
          ▼
┌─────────────────────────────────────────────────────────┐
│ mt5pipe.ingestion                                       │
│  • backfill (resumable)                                 │
│  • live stream                                          │
│  • mt5.connection, mt5.adapters                         │
└─────────┬───────────────────────────────────────────────┘
          │ parquet (partitioned)
          ▼
┌─────────────────────────────────────────────────────────┐
│ mt5pipe.merge → canonical ticks (audit-preserving)      │
│ mt5pipe.bars  → multi-timeframe bars                    │
│ mt5pipe.quality → merge_qa, bucket sweeps               │
└─────────┬───────────────────────────────────────────────┘
          │ canonical bars + state artifacts
          ▼
┌─────────────────────────────────────────────────────────┐
│ mt5pipe.compiler  (Phase 1 dataset compiler)            │
│  state → feature_view → label_view → dataset            │
│ mt5pipe.catalog (sqlite) + mt5pipe.truth (gate)         │
└─────────┬───────────────────────────────────────────────┘
          │ truth-gated dataset aliases
          ▼
┌─────────────────────────────────────────────────────────┐
│ aphelion.feature_engine (event-driven, replay-safe)     │
│  TickEvent / BarCloseEvent → FeatureSnapshot (107-D)   │
│  integrations.mt5pipe bridge                            │
└─────────┬───────────────────────────────────────────────┘
          │ FeatureSnapshot
          ▼
┌─────────────────────────────────────────────────────────┐
│ machinelearning                                         │
│  data.datamodule/dataset → training.train               │
│  regime.detector/moe → signal.publisher+conformal       │
│  [★ BROKEN: machinelearning.models missing]             │
└─────────┬───────────────────────────────────────────────┘
          │ ModelOutput (multi-horizon: 5/15/60/240m)
          ▼
┌─────────────────────────────────────────────────────────┐
│ aphelion.integrations.supersystem                       │
│  feature_bridge   → rolling snapshot history            │
│  signal_bridge    → NeuralSignalEngine [★ BROKEN]       │
│  event_pipeline   → EventDrivenSuperSystem              │
│  execution_bridge → SuperExecutionStack                 │
└─────────┬───────────────────────────────────────────────┘
          │ Signal (calibrated, regime-aware)
          ▼
┌─────────────────────────────────────────────────────────┐
│ aphelion.intelligence.hydra  (ensemble wrapper)         │
│  TFT + LSTM + CNN + TCN + MoE + XGB + Transformer       │
│  inference.py / strategy.py / adversarial               │
└─────────┬───────────────────────────────────────────────┘
          │ gated signal
          ▼
┌─────────────────────────────────────────────────────────┐
│ aphelion.risk.sentinel (v2)                             │
│  position_sizer + circuit_breaker + validator           │
│  + titan gate (stress/stability/regression/perf/latency)│
└─────────┬───────────────────────────────────────────────┘
          │ sized order
          ▼
┌─────────────────────────────────────────────────────────┐
│ aphelion.ares.coordinator → order journal               │
│ aphelion.paper.runner / MT5 execution (sentinel/mt5.py) │
└─────────────────────────────────────────────────────────┘

Governance overlay (observes every stage):
  olympus.orchestrator → council (sola/veto/edge_decay/regime_awareness)
  nemesis (chronos/leviathan/pandora/verdict/stress_monitor) ← adversarial probes
  evolution (zeus/cipher/meridian/prometheus) ← offline search on genome space
```

### D.2 Critical path for backtest vs live

- **Backtest:** `mt5pipe` (stored) → `feature_engine.replay` → `aphelion.backtest.engine` (event-driven) + `walk_forward.py` + `monte_carlo.py` → metrics.
- **Live:** same `feature_engine` (replay-safe claim) → supersystem.signal_bridge → sentinel → `paper.runner` / MT5.
- **Shared hot path** — `feature_engine` designed for single-process, deterministic, replay-safe identical code in live and replay (per FEATURE_ENGINE_DESIGN.md §1).

### D.3 Orphaned / unclear lineage

| Module | Status | Notes |
|---|---|---|
| `aphelion/macro/{argus,atlas,herald,nexus,oracle}` | Unclear | 5 macro submodules; no doc surfaces purpose of each |
| `aphelion/flow/{phantom,specter}` | Unclear | flow analysis but no clear consumer |
| `aphelion/nemesis/{leviathan,pandora}` | Unclear | adversarial but no driver |
| `aphelion/money/` | Unclear | money management layer — sizing already in sentinel |
| `aphelion/aphelion_model/` | Artifact | model storage dir; inspect for stray checkpoints |
| `cpp-cooker/` | Separate stack | v1.0.0 sim engine (C++/QuantLib). No pybind binding visible — is it wired? |

---

## SECTION E — GAPS vs INSTITUTIONAL QUANT STANDARDS

| Feature | Present? | Notes |
|---|---|---|
| Multi-asset / portfolio | ✗ | XAU/USD only |
| Portfolio-level risk (VaR, Greeks, corr-adjusted) | ✗ | position-level sizer only |
| Regime detection | ✓ | `machinelearning/regime/` (detector, labeler, moe, features) |
| Walk-forward validation | ✓ | `backtest/walk_forward.py` |
| Monte Carlo / stress | ✓ | `backtest/monte_carlo.py` + titan/stress |
| Cost / slippage / commission | ~ | backtest/broker_sim.py + sentinel but no verified calibration harness |
| TCA / execution quality | ~ | almgren_chriss present; no post-trade analyzer |
| Market microstructure features | ✓ | `feature_engine/features/microstructure` + MICROSTRUCTURE_FEATURES.md |
| Order book depth / L2 | ✗ | MT5 tick-only |
| Latency instrumentation | ~ | titan/latency validator but no p99 harness in tests |
| Monitoring / alerting dashboard | ✗ | TUI only (local), no Grafana/Prom |
| CI/CD, pre-commit, lint gate | ✗ | pyproject exists, no workflows |
| Type checking (mypy/pyright) | ✗ | No config surfaced |
| Code coverage gate | ~ | pytest-cov in deps, no enforced threshold |
| Disaster recovery / failover | ✗ | no hot-standby visible |
| Compliance / audit log | ~ | ares/journal + feedbacks inbox informal |
| LLM latency / cost modeling | ✗ | `hephaestus/llm_client` but no live cost gate |
| Reproducibility (seed, env lock) | ~ | requirements.txt pinned, no env lockfile (pip-tools / uv) |
| Secrets management | ✓ | `.env.example` only, no inline keys |
| Multi-signal aggregation | ✓ | HYDRA ensemble + supersystem gating |
| Conformal prediction / calibration | ✓ | `machinelearning/signal/conformal.py` |
| Live risk circuit breakers | ✓ | sentinel/circuit_breaker + validator |

**Top 5 infrastructure gaps:**
1. CI/CD + test-gate + lint + mypy → zero currently.
2. Portfolio risk layer (cross-asset correlations, VaR, concentration).
3. Post-trade TCA loop with slippage/fill-quality feedback into sizer.
4. Observability stack beyond TUI (metrics exporter, SLO dashboards).
5. L2 / order-book microstructure (currently tick-only).

---

## SECTION F — CONSOLIDATION ROADMAP

### F.1 Week 1 — high-risk cleanups (delete + restore)

1. **Delete exact dups**
   - `C:\aphelion\GIGA-NI-main (4).zip` (byte-identical to (3))
   - `giga-ni/codex_temp/` (48 KB scratch)
2. **Restore missing ML models** (FIX BROKEN BUILD)
   - Copy `aphelion-neural/machinelearning/models/{__init__,base,blocks,tft,ablation,interpret}.py` → `giga-ni/machinelearning/models/`
   - Run `pytest machinelearning/tests/ aphelion/integrations/tests/ -v` and fix drift.
3. **Retire predecessor repos** — archive `Aphelion-Reasearch-main.zip`, `Aphelion-nueral-main.zip`, `DataPipeline-main.zip`, `Future-engine-main.zip` into `_archive/` folder with dated tag. Do NOT delete until giga-ni build is green.
4. **Hash-diff drifted files** — 45 aphelion-research + 57 aphelion-neural + 25 datapipeline unabsorbed hashes: diff each against giga-ni counterpart; either port the newer logic or mark explicitly superseded.

### F.2 Week 2-3 — dedupe + consolidate

1. **Merge `aphelion/features/` → `aphelion/feature_engine/`**
   - Move `microstructure`, `market_structure`, `volume_profile`, `vwap`, `cross_impact`, `cointegration`, `signature`, `mtf`, `engine` under `feature_engine/features/` (already-exist check).
   - Delete dead modules: `halftrend.py`, `registry.py`, `sessions.py` (0 inbound refs).
   - Replace remaining imports.
2. **Remove entry-point shims** — `aphelion.py`, `run_paper.py`, `runall.py` at root; enforce `python -m aphelion` / `aphelion-paper` / `aphelion-demo` console scripts.
3. **Collapse `aphelion_data.py` monolith** — split into
   - `scripts/fetch_all.py` (ingestion driver using mt5pipe.backfill)
   - `scripts/build_features.py` (feature_engine replay)
   - `scripts/train_hydra.py` (thin wrapper over `machinelearning.training.train`)
4. **Move dev tools** — `map.py` → `scripts/dev/project_map.py`; `sxcas.py` → `scripts/dev/scan_processes.py`.
5. **Resolve triplicate `mt5pipe`** — ensure only `giga-ni/mt5pipe/` exists post-archive.

### F.3 Week 4-6 — quality + CI

1. **Add `.github/workflows/ci.yml`** — `pytest + mypy + ruff + pytest-cov`. Target ≥ 70 % coverage on `aphelion/core`, `feature_engine`, `mt5pipe/compiler`, `machinelearning/*`, `risk/sentinel`.
2. **Type hint push** — 48 % → 80 %. Start with `aphelion/core`, `feature_engine`, public APIs.
3. **Replace 90 `print(` calls** with structlog (already in deps).
4. **Lockfile** — `uv lock` or `pip-compile` → `requirements.lock`.
5. **Pre-commit** — ruff + mypy + pytest-fast.

### F.4 Month 2-3 — institutional features

1. **Portfolio risk layer** — cross-asset correlation, VaR, concentration limits above sentinel.
2. **Post-trade TCA** — slippage / fill-quality tracker; feed into sizer + sentinel validators.
3. **Observability** — Prometheus exporter → dashboards (beyond TUI).
4. **Multi-asset generalization** — strip XAU/USD assumptions from features + configs; parametrize by instrument.
5. **Hephaestus cost gate** — track LLM latency/cost per call; block on SLO breach.
6. **Reg-awareness end-to-end test** — regime.detector → moe → signal → sentinel through 3 historical regimes (trend / MR / vol).

---

## SECTION G — APPENDICES

### G.1 Files absorbed but drifted (need diff review)

**aphelion-research (45 unabsorbed hashes):** all files correspond to paths present in giga-ni → pure drift. High-priority diff targets: `aphelion/features/engine.py`, `aphelion/backtest/engine.py`, `aphelion/core/event_bus.py`, `aphelion/core/data_layer.py`, `aphelion/intelligence/hydra/strategy.py`, `aphelion/paper/runner.py`, `aphelion/paper/session.py`, `aphelion/risk/titan/gate.py`, `aphelion/evolution/meridian/engine.py`, `aphelion/evolution/prometheus/evaluator.py`.

**aphelion-neural (57 unabsorbed):** `machinelearning/models/*` (6 files — MUST RESTORE), `APH/backtest/*` (pre-rename, superseded by `machinelearning/backtest/`), `machinelearning/signal/{publisher,records}.py`, multiple `data/mt5pipe/*` (stale mt5pipe dup).

**datapipeline (25 unabsorbed):** `mt5pipe/{truth,compiler}/service.py` drift; `tests/test_state_boundaries.py`, `tests/test_boundary_imports.py` — check if tests lost.

**future-engine (4 unabsorbed):** trivial `__init__.py`.

### G.2 Dead-code candidates

- `giga-ni/aphelion/features/halftrend.py` — 0 inbound
- `giga-ni/aphelion/features/registry.py` — 0 inbound
- `giga-ni/aphelion/features/sessions.py` — 0 inbound
- `giga-ni/codex_temp/*` — all scratch
- `giga-ni/config/legacy-packaging/` — archived snapshots (confirm no consumer)

### G.3 Top-level giga-ni docs (present)

- README.md (strong)
- AGENTS.md (repo guidelines)
- AI_CONTEXT.md (context order for AI agents)
- FEATURE_ENGINE_DESIGN.md (architecture spec)
- INFERENCE_HANDOFF.md (107-D contract + normalization rules)
- MICROSTRUCTURE_FEATURES.md
- MT5PIPE_INTEGRATION.md

### G.4 Requirements audit (giga-ni)

Clean modern stack — torch≥2, scikit≥1.5, xgboost/lightgbm, optuna, shap, polars, pyarrow, pydantic v2, structlog, loguru, rich, textual, pytest+asyncio+cov, hypothesis. Versions floor-pinned (`>=`), not lockfile-pinned — upgrade drift risk.

---

## RECOMMENDATIONS — PRIORITIZED BY IMPACT

1. **[P0] Fix broken ML path.** Port `machinelearning/models/` into giga-ni; run ML + supersystem test dirs.
2. **[P0] Add CI.** Minimum: `pytest + ruff` on push/PR. Zero today.
3. **[P1] Delete dup zip (GIGA-NI (4)), `codex_temp/`, dead feature modules.**
4. **[P1] Collapse legacy `features/` into `feature_engine/`.**
5. **[P1] Split `aphelion_data.py` into 3 focused scripts.**
6. **[P2] Raise type-hint coverage 48 → 80 %.** Start with public APIs.
7. **[P2] Replace 90 `print(` with structlog.**
8. **[P2] Archive predecessor repos (aphelion-research, aphelion-neural, datapipeline, future-engine) under `_archive/` after drift-diff pass.**
9. **[P3] Portfolio risk layer + multi-asset generalization.**
10. **[P3] Post-trade TCA + observability stack beyond TUI.**

---

**End of report.**
