"""
Subprocess bridge: calls the C++ aphelion binary and parses results.

The C++ binary lives at: dominion/cpp/build/Release/aphelion.exe (Windows)
or dominion/cpp/build/aphelion (Linux/macOS, when built).

Results are read from JSON/CSV output files written by the C++ engine.
"""
from __future__ import annotations

import json
import subprocess
import structlog
import pandas as pd
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = structlog.get_logger(__name__)

# Default binary location — override via DOMINION_CPP_BIN env var or constructor
DEFAULT_CPP_BIN = (
    Path(__file__).parent.parent.parent.parent
    / "cpp"
    / "build"
    / "Release"
    / "aphelion.exe"
)


@dataclass
class HydraEvolutionFinalist:
    """A finalist genome from the C++ Hydra evolution."""

    param_id:         int
    monthly_return:   float
    total_return:     float
    max_drawdown:     float
    profit_factor:    float
    win_rate:         float
    trade_count:      int
    consistency:      float
    composite_score:  float
    robustness_score: float
    params:           dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict) -> "HydraEvolutionFinalist":
        return cls(
            param_id=d.get("param_id", 0),
            monthly_return=d.get("monthly_return", 0.0),
            total_return=d.get("total_return", 0.0),
            max_drawdown=d.get("max_drawdown", 0.0),
            profit_factor=d.get("profit_factor", 0.0),
            win_rate=d.get("win_rate", 0.0),
            trade_count=d.get("trade_count", 0),
            consistency=d.get("consistency", 0.0),
            composite_score=d.get("composite_score", 0.0),
            robustness_score=d.get("robustness_score", 0.0),
            params=d.get("params", {}),
        )


@dataclass
class TournamentResult:
    """Results from a C++ tournament run."""

    bars_processed:    int
    total_fills:       int
    elapsed_seconds:   float
    bars_per_sec:      float
    acct_bars_per_sec: float
    summary_csv:       pd.DataFrame | None = None
    metadata:          dict[str, Any] = field(default_factory=dict)


class CppRunner:
    """
    Calls the C++ aphelion simulation binary via subprocess.

    Usage::

        runner = CppRunner(
            data_root=Path(r"C:\\Users\\marti\\LLM\\data_sim_ready"),
            output_dir=Path("output/cpp"),
        )

        # Quick tournament to verify signal tape
        result = runner.run_tournament(
            symbol="XAUUSD",
            timeframe="H1",
            hydra_tape=Path("signals/signal_tape_XAUUSD_H1.parquet"),
            accounts=50,
        )

        # Full evolution
        finalists = runner.run_hydra_evolution(
            symbol="XAUUSD",
            timeframe="H1",
            hydra_tape=Path("signals/signal_tape_XAUUSD_H1.parquet"),
            population=200,
            generations=50,
        )
    """

    def __init__(
        self,
        data_root: Path,
        output_dir: Path = Path("output/cpp"),
        cpp_bin: Path | None = None,
    ) -> None:
        self.data_root  = Path(data_root)
        self.output_dir = Path(output_dir)
        self.cpp_bin    = Path(cpp_bin) if cpp_bin else DEFAULT_CPP_BIN

        if not self.cpp_bin.exists():
            log.warning(
                "cpp_binary_not_found",
                path=str(self.cpp_bin),
                hint=(
                    "Build with: cd dominion/cpp && "
                    "cmake -B build && cmake --build build --config Release"
                ),
            )

    def _run(
        self, args: list[str], timeout: int = 3600
    ) -> subprocess.CompletedProcess:
        cmd = [str(self.cpp_bin)] + args
        log.info("cpp_runner_start", cmd=" ".join(cmd))
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        if result.returncode != 0:
            log.error("cpp_runner_failed", stderr=result.stderr[-2000:])
            raise RuntimeError(
                f"C++ binary failed (code {result.returncode}):\n"
                f"{result.stderr[-1000:]}"
            )
        return result

    def run_tournament(
        self,
        symbol: str = "XAUUSD",
        timeframe: str = "H1",
        context_timeframes: list[str] | None = None,
        hydra_tape: Path | None = None,
        accounts: int = 100,
        leverage: float = 100.0,
        risk: float = 0.01,
        mode: str = "research",
        output_subdir: str = "tournament",
    ) -> TournamentResult:
        """Run a tournament (parameter sweep) on real or HYDRA-signal-driven strategy."""
        out = self.output_dir / output_subdir
        out.mkdir(parents=True, exist_ok=True)

        args = [
            "--data-root", str(self.data_root),
            "--symbol",    symbol,
            "--timeframe", timeframe,
            "--accounts",  str(accounts),
            "--leverage",  str(leverage),
            "--risk",      str(risk),
            "--mode",      mode,
            "--output",    str(out),
        ]
        if context_timeframes:
            for tf in context_timeframes:
                args += ["--context-tf", tf]
        if hydra_tape:
            args += ["--hydra-tape", str(hydra_tape)]

        proc = self._run(args)
        return self._parse_tournament_result(out, proc.stdout)

    def run_hydra_evolution(
        self,
        symbol: str = "XAUUSD",
        timeframe: str = "H1",
        context_timeframes: list[str] | None = None,
        hydra_tape: Path | None = None,
        population: int = 200,
        generations: int = 50,
        elite_count: int = 10,
        mutation_rate: float = 0.20,
        min_monthly_return: float = 0.05,
        max_drawdown: float = 0.20,
        min_profit_factor: float = 1.15,
        leverage: float = 100.0,
        risk: float = 0.01,
        seed: int = 42,
        output_subdir: str = "hydra_evolution",
    ) -> list[HydraEvolutionFinalist]:
        """Run the Hydra-signal evolution to find optimal execution params."""
        if hydra_tape is None:
            raise ValueError("hydra_tape path is required for run_hydra_evolution")

        out = self.output_dir / output_subdir
        out.mkdir(parents=True, exist_ok=True)

        args = [
            "--data-root",          str(self.data_root),
            "--symbol",             symbol,
            "--timeframe",          timeframe,
            "--hydra-tape",         str(hydra_tape),
            "--hydra-evolve",
            "--pop-size",           str(population),
            "--generations",        str(generations),
            "--elite-count",        str(elite_count),
            "--mutation-rate",      str(mutation_rate),
            "--min-monthly-return", str(min_monthly_return),
            "--max-drawdown",       str(max_drawdown),
            "--min-profit-factor",  str(min_profit_factor),
            "--leverage",           str(leverage),
            "--risk",               str(risk),
            "--evolution-seed",     str(seed),
            "--evolution-output",   str(out),
        ]
        if context_timeframes:
            for tf in context_timeframes:
                args += ["--context-tf", tf]

        self._run(args)
        return self._parse_finalists(out / "finalists.json")

    def _parse_tournament_result(
        self, out_dir: Path, stdout: str
    ) -> TournamentResult:
        summary_csv = None
        csv_path = out_dir / "summary.csv"
        if csv_path.exists():
            summary_csv = pd.read_csv(csv_path)

        meta: dict[str, Any] = {}
        meta_path = out_dir / "run_metadata.json"
        if meta_path.exists():
            meta = json.loads(meta_path.read_text())

        bars_per_sec = 0.0
        acct_bars_per_sec = 0.0
        for line in stdout.splitlines():
            if "Bars/sec:" in line:
                try:
                    bars_per_sec = float(line.split(":")[-1].strip())
                except ValueError:
                    pass
            if "Acct*Bars/sec:" in line:
                try:
                    acct_bars_per_sec = float(line.split(":")[-1].strip())
                except ValueError:
                    pass

        return TournamentResult(
            bars_processed=meta.get("total_bars", 0),
            total_fills=meta.get("total_fills", 0),
            elapsed_seconds=meta.get("elapsed_seconds", 0.0),
            bars_per_sec=bars_per_sec,
            acct_bars_per_sec=acct_bars_per_sec,
            summary_csv=summary_csv,
            metadata=meta,
        )

    def _parse_finalists(self, path: Path) -> list[HydraEvolutionFinalist]:
        if not path.exists():
            log.warning("finalists_json_not_found", path=str(path))
            return []
        data = json.loads(path.read_text())
        finalists = [HydraEvolutionFinalist.from_dict(d) for d in data]
        log.info("finalists_loaded", count=len(finalists), path=str(path))
        return finalists
