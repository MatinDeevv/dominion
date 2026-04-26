# GIGA-NI CI/CD Pipeline

## Overview

- Pushes to `main` and `develop` run the primary quality gate workflow.
- Pull requests into `main` and `develop` run the same checks before merge.
- Nightly automation runs the backtest suite and the feature-engine latency benchmark.

## Workflows

### `ci.yml`

Runs on every push and pull request.

- `test`: executes `tests/` and `machinelearning/tests/` with coverage for `aphelion`, `machinelearning`, and `mt5pipe`
- `type-check`: runs `pyright` across the core Python packages
- `lint`: runs `ruff check` and `ruff format --check`
- `code-quality`: rejects executable `print()` calls in `aphelion/` and rejects bare `except:`
- `summary`: fails the workflow if any required job fails

### `nightly.yml`

Runs daily at 2 AM UTC and can also be triggered manually.

- `backtest-regression`: runs `tests/backtest/`
- `performance-check`: runs `scripts/benchmark_inference.py` and enforces the `<50ms` latency budget

## Coverage Baseline

- Established: 2026-04-20
- Combined baseline for `tests/` + `machinelearning/tests/`: see `coverage.json` / CI artifact after the first CI run
- Current target: `>= 70%`
- Recommended minimum: `>= 50%`

## Local Development

Run this before opening a pull request:

```bash
make check-all
```

Useful shortcuts:

```bash
make test
make lint
make types
make backtest
```

## Branch Protection

Apply these rules in GitHub repository settings for both `main` and `develop`:

- Require a pull request before merging
- Require at least 1 approval
- Require branches to be up to date before merging
- Require these status checks to pass:
  - `Unit Tests & Coverage`
  - `Type Checking (pyright)`
  - `Linting (ruff)`
  - `Code Quality Checks`
  - `CI Summary`

## Notes

- `scripts/compare_backtest_results.py` compares serialized backtest outputs against a baseline.
- `scripts/benchmark_inference.py` benchmarks the canonical feature-engine path used for inference snapshots.
- This repo currently uses an AST-based `print()` gate in CI so docstring examples do not trigger false failures.
