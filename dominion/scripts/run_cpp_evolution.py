"""
End-to-end orchestration: HYDRA inference → signal tape → C++ evolution.

Usage::

    python scripts/run_cpp_evolution.py \\
        --symbol XAUUSD \\
        --timeframe H1 \\
        --data-root "C:\\Users\\marti\\LLM\\data_sim_ready" \\
        --bars-parquet "C:\\Users\\marti\\LLM\\data_sim_ready\\XAUUSD\\H1\\data.parquet" \\
        --model-checkpoint "models/hydra_xauusd_h1_latest.pt" \\
        --output-dir output/evolution \\
        --population 200 \\
        --generations 50

Steps:
    1. Load bars from Parquet via mt5pipe
    2. Build FeatureSnapshots via feature_engine
    3. Run HYDRA inference on all bars
    4. Export signal tape to Parquet
    5. Call C++ HydraEvolutionEngine via CppRunner
    6. Load and display finalists
"""
from __future__ import annotations

import sys
import typer
import structlog
import pandas as pd
from pathlib import Path

app = typer.Typer()
log = structlog.get_logger(__name__)


@app.command()
def main(
    symbol:           str   = typer.Option("XAUUSD"),
    timeframe:        str   = typer.Option("H1"),
    data_root:        Path  = typer.Option(..., help="C++ data root (bar Parquet files)"),
    bars_parquet:     Path  = typer.Option(..., help="Primary bar Parquet for Python inference"),
    model_checkpoint: Path  = typer.Option(..., help="HYDRA model checkpoint (.pt)"),
    output_dir:       Path  = typer.Option(Path("output/evolution")),
    population:       int   = typer.Option(200),
    generations:      int   = typer.Option(50),
    context_tfs:      list[str] = typer.Option([], "--context-tf"),
    confidence_min:   float = typer.Option(0.40, help="Min confidence to include in tape"),
    skip_inference:   bool  = typer.Option(False, help="Skip inference if tape already exists"),
    cpp_bin:          Path | None = typer.Option(None, help="Path to C++ binary"),
) -> None:

    output_dir.mkdir(parents=True, exist_ok=True)
    signal_tape_path = output_dir / f"signal_tape_{symbol}_{timeframe}.parquet"

    # ── Step 1-4: Inference + export ────────────────────────
    if skip_inference and signal_tape_path.exists():
        log.info("skipping_inference", tape=str(signal_tape_path))
    else:
        log.info("loading_bars", path=str(bars_parquet))
        import pyarrow.parquet as pq
        bars_df = pq.read_table(bars_parquet).to_pandas()
        log.info("bars_loaded", count=len(bars_df))

        log.info("building_feature_snapshots")
        from aphelion.feature_engine.engine import FeatureEngine
        from aphelion.core.config import load_config
        cfg = load_config()
        engine = FeatureEngine(cfg)
        snapshots = engine.build_batch(bars_df)
        log.info("snapshots_built", count=len(snapshots))

        log.info("running_hydra_inference", checkpoint=str(model_checkpoint))
        from aphelion.intelligence.hydra.inference import HydraInferenceEngine
        hydra = HydraInferenceEngine.from_checkpoint(model_checkpoint)
        results = hydra.infer_batch(snapshots)
        log.info("inference_complete", count=len(results))

        log.info("exporting_signal_tape")
        import numpy as np
        from aphelion.intelligence.hydra.signal_exporter import export_signal_tape

        # Convert bar timestamps to milliseconds
        if "time" in bars_df.columns:
            timestamps_ms = (
                pd.to_datetime(bars_df["time"]).astype("int64") // 1_000_000
            ).values
        elif "time_ms" in bars_df.columns:
            timestamps_ms = bars_df["time_ms"].values.astype("int64")
        else:
            raise ValueError("No 'time' or 'time_ms' column found in bars Parquet")

        export_signal_tape(
            results=results,
            timestamps_ms=timestamps_ms,
            output_path=output_dir,
            symbol=symbol,
            timeframe=timeframe,
            confidence_threshold=confidence_min,
        )
        log.info("signal_tape_exported", path=str(signal_tape_path))

    # ── Step 5: C++ evolution ────────────────────────────────
    log.info("starting_cpp_evolution", population=population, generations=generations)
    from aphelion.evolution.cpp_runner import CppRunner

    runner = CppRunner(
        data_root=data_root,
        output_dir=output_dir / "cpp",
        cpp_bin=cpp_bin,
    )

    finalists = runner.run_hydra_evolution(
        symbol=symbol,
        timeframe=timeframe,
        context_timeframes=context_tfs if context_tfs else None,
        hydra_tape=signal_tape_path,
        population=population,
        generations=generations,
    )

    # ── Step 6: Display results ──────────────────────────────
    if not finalists:
        log.warning(
            "no_finalists_found",
            hint="Lower thresholds or increase population/generations",
        )
        sys.exit(1)

    print(f"\n{'='*70}")
    print(f"  HYDRA EVOLUTION FINALISTS — {symbol} {timeframe}")
    print(f"{'='*70}")
    print(
        f"  {'Rank':<5} {'MonthRet':>9} {'MaxDD':>8} {'PF':>7} "
        f"{'WR':>7} {'Trades':>7} {'Score':>8}"
    )
    print(f"  {'-'*60}")
    for i, f in enumerate(finalists[:20], 1):
        print(
            f"  {i:<5} {f.monthly_return*100:>8.1f}% {f.max_drawdown*100:>7.1f}% "
            f"{f.profit_factor:>7.2f} {f.win_rate*100:>6.1f}% "
            f"{f.trade_count:>7} {f.composite_score:>8.3f}"
        )
    print(f"{'='*70}\n")

    if finalists:
        best = finalists[0]
        print("BEST PARAMS:")
        for k, v in best.params.items():
            print(f"  {k}: {v}")

    log.info("evolution_complete", finalists=len(finalists))


if __name__ == "__main__":
    app()
