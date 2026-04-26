## AI Context Guide

Use this repo like this if you want fast, high-signal AI context:

- Start with `README.md` and `AGENTS.md`.
- Read core runtime code in `aphelion/`, `mt5pipe/`, `machinelearning/`, and `config/`.
- Use `tests/` selectively for behavior, not as default bulk context.
- Ignore archived local artifacts, logs, chat dumps, feedback dumps, notebooks, and large generated maps.

Recommended order:

1. `README.md`
2. `AGENTS.md`
3. `aphelion/`
4. `mt5pipe/`
5. `machinelearning/`
6. `config/`
7. `tests/` only for the module you are changing

Low-value context for most AI coding tasks:

- `agent-tools/`
- `chat/`
- `feedbacks/`
- `legacy/`
- `logs/`
- `tmp/`
- `notebooks/`
- `aphelion_full_map.txt`
- bundled model artifacts such as `aphelion/aphelion_model.zip`

Canonical entrypoints:

- `python -m aphelion` or `aphelion` for the unified runtime
- `aphelion-paper` for package-owned paper trading launch
- `aphelion-demo` for the package-owned demo launch
- `aphelion-tui` for the package-owned TUI launch
- `mt5pipe-super` or `python -m mt5pipe.tools.super_pipeline_tui` for the MT5 pipeline operator TUI

Compatibility shims still exist at repo root for now:

- `aphelion.py`
- `run_paper.py`
- `runall.py`
- `scripts/super_pipeline_tui.py`

Treat those as temporary wrappers, not canonical module owners.
