# APHELION

Unified root project for the APHELION trading stack.

This workspace combines:

- `aphelion/`
  Core runtime, governance, risk, paper execution, backtesting, feature-engine integration, and the supersystem bridge layer.

- `mt5pipe/`
  MetaTrader 5 ingestion, canonical market data fusion, dataset compilation, and truth-gated publication.

- `machinelearning/`
  Neural data handling, canonical ML backtesting helpers, training, inference batch contracts, regime logic, and calibrated signal publishing.

## Root Layout

- `config/`
  Runtime config plus archived packaging snapshots from the original split repos.

- `docs/`
  Main documentation and archived legacy READMEs.

- `chat/`
  Preserved project notes from the former neural and pipeline repos.

- `feedbacks/`
  Preserved project feedback artifacts from the former neural and pipeline repos.

- `legacy/neural-data-pipeline/`
  Archived embedded MT5/data-pipeline snapshot that used to live inside the neural repo.

## Install

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Or install in editable mode:

```powershell
pip install -e .[all]
```

## Tests

```powershell
python -m pytest tests -q
```

## Unified CLI

```powershell
python -m aphelion status --config config\backtest.yaml
python -m aphelion config validate --config config\backtest.yaml
python -m aphelion backtest --config config\backtest.yaml
python -m aphelion paper --config config\paper.yaml
python -m aphelion live --config config\live.yaml
```

The package CLI wraps the merged runtime:

- `backtest`
  Replays MT5Pipe data through the unified event-driven supersystem.

- `paper`
  Runs the paper-trading stack with the merged APHELION runtime.

- `live`
  Uses the paper/live runner wiring with MT5 connection settings from config.

## Notes

- The old top-level repo folders were intentionally flattened into this root project.
- Original per-repo READMEs live in `docs/legacy-readmes/`.
- Original per-repo packaging files live in `config/legacy-packaging/`.
