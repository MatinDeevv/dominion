# DOMINION C++ Integration Plan

The `cpp/` tree is reserved for the QuantLib-backed simulation engine. It is a standalone C++ backend until a Python binding is added.

## Module Map

| C++ module | Python module | Role |
| --- | --- | --- |
| `replay_engine` | `aphelion.backtest.engine` and `aphelion.evolution.cpp_backend.run_replay` | Historical replay, order simulation, cost/slippage accounting |
| `evolution_engine` | `aphelion.evolution.prometheus.engine` and `aphelion.evolution.cpp_backend.run_evolution` | Fast genome/evolution evaluation loop |
| `risk_engine` | `aphelion.risk.sentinel` and `aphelion.risk.titan` | Position/risk gates, drawdown stops, validation metrics |
| `stress_engine` | `aphelion.evolution.zeus.engine` | Stress scenarios and replay perturbations |

## Proposed pybind11 Interface

```cpp
py::dict run_replay(
    py::list bars,
    py::dict config,
    py::dict risk_config,
    py::dict execution_config
);

py::dict run_evolution(
    py::dict genome_config,
    py::dict evaluation_config,
    py::list training_windows
);
```

Data should cross the boundary as plain Python containers first: `dict`, `list`, `float`, `int`, and ISO-8601 timestamp strings. Once stable, migrate hot paths to NumPy buffers or Arrow tables.

## Build Requirements

- QuantLib
- pybind11
- CMake 3.20+
- vcpkg toolchain for Windows dependency resolution
- Python 3.12 development headers matching `pyproject.toml`

## Binding Steps

1. Add pybind11 to `CMakeLists.txt` and `vcpkg.json`.
2. Write `cpp/src/bindings.cpp` exposing `replay_engine` and `evolution_engine`.
3. Add and keep `aphelion/evolution/cpp_backend.py` as the Python wrapper, falling back to pure-Python engines when `_dominion_cpp` is not built.

