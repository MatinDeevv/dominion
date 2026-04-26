from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_results(path: Path) -> dict[str, float]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare backtest JSON results against a baseline.")
    parser.add_argument("--baseline", type=Path, required=True, help="Baseline backtest results JSON")
    parser.add_argument("--current", type=Path, required=True, help="Current backtest results JSON")
    parser.add_argument("--tolerance", type=float, default=5.0, help="Tolerance percentage")
    args = parser.parse_args()

    baseline = load_results(args.baseline)
    current = load_results(args.current)

    baseline_pnl = float(baseline.get("final_pnl", 0.0))
    current_pnl = float(current.get("final_pnl", 0.0))
    variance = ((current_pnl - baseline_pnl) / abs(baseline_pnl) * 100.0) if baseline_pnl else 0.0

    print(f"Baseline PnL: ${baseline_pnl:.2f}")
    print(f"Current PnL: ${current_pnl:.2f}")
    print(f"Variance: {variance:.2f}%")

    if abs(variance) > args.tolerance:
        print(f"REGRESSION: variance exceeds tolerance ({args.tolerance:.2f}%)")
        return 1

    print("OK: variance within tolerance")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
