"""APHELION backtest package."""

__all__ = [
    # Engine
    "BacktestEngine",
    "BacktestConfig",
    "BacktestResults",
    # Broker
    "BrokerSimulator",
    "BrokerConfig",
    # Portfolio
    "Portfolio",
    # Orders
    "Order",
    "OrderType",
    "OrderSide",
    "OrderStatus",
    "Fill",
    "BacktestTrade",
    # Metrics
    "BacktestMetrics",
    "compute_metrics",
    "sharpe_ratio",
    "sortino_ratio",
    "calmar_ratio",
    "omega_ratio",
    "profit_factor",
    "max_drawdown",
    # Monte Carlo
    "MonteCarloEngine",
    "MonteCarloConfig",
    "MonteCarloResults",
    # Walk-Forward
    "WalkForwardEngine",
    "WalkForwardConfig",
    "WalkForwardResults",
    "WalkForwardWindow",
]


def __getattr__(name: str):
    if name in {"BacktestEngine", "BacktestConfig", "BacktestResults"}:
        from aphelion.backtest.engine import BacktestConfig, BacktestEngine, BacktestResults

        return {
            "BacktestEngine": BacktestEngine,
            "BacktestConfig": BacktestConfig,
            "BacktestResults": BacktestResults,
        }[name]

    if name in {"BrokerSimulator", "BrokerConfig"}:
        from aphelion.backtest.broker_sim import BrokerConfig, BrokerSimulator

        return {"BrokerSimulator": BrokerSimulator, "BrokerConfig": BrokerConfig}[name]

    if name == "Portfolio":
        from aphelion.backtest.portfolio import Portfolio

        return Portfolio

    if name in {"Order", "OrderType", "OrderSide", "OrderStatus", "Fill", "BacktestTrade"}:
        from aphelion.backtest.order import BacktestTrade, Fill, Order, OrderSide, OrderStatus, OrderType

        return {
            "Order": Order,
            "OrderType": OrderType,
            "OrderSide": OrderSide,
            "OrderStatus": OrderStatus,
            "Fill": Fill,
            "BacktestTrade": BacktestTrade,
        }[name]

    if name in {
        "BacktestMetrics",
        "compute_metrics",
        "sharpe_ratio",
        "sortino_ratio",
        "calmar_ratio",
        "omega_ratio",
        "profit_factor",
        "max_drawdown",
    }:
        from aphelion.backtest.metrics import (
            BacktestMetrics,
            calmar_ratio,
            compute_metrics,
            max_drawdown,
            omega_ratio,
            profit_factor,
            sharpe_ratio,
            sortino_ratio,
        )

        metric_exports = {
            "BacktestMetrics": BacktestMetrics,
            "compute_metrics": compute_metrics,
            "sharpe_ratio": sharpe_ratio,
            "sortino_ratio": sortino_ratio,
            "calmar_ratio": calmar_ratio,
            "omega_ratio": omega_ratio,
            "profit_factor": profit_factor,
            "max_drawdown": max_drawdown,
        }
        return metric_exports[name]

    if name in {"MonteCarloEngine", "MonteCarloConfig", "MonteCarloResults"}:
        from aphelion.backtest.monte_carlo import MonteCarloConfig, MonteCarloEngine, MonteCarloResults

        return {
            "MonteCarloEngine": MonteCarloEngine,
            "MonteCarloConfig": MonteCarloConfig,
            "MonteCarloResults": MonteCarloResults,
        }[name]

    if name in {
        "WalkForwardEngine",
        "WalkForwardConfig",
        "WalkForwardResults",
        "WalkForwardWindow",
    }:
        from aphelion.backtest.walk_forward import (
            WalkForwardConfig,
            WalkForwardEngine,
            WalkForwardResults,
            WalkForwardWindow,
        )

        wf_exports = {
            "WalkForwardEngine": WalkForwardEngine,
            "WalkForwardConfig": WalkForwardConfig,
            "WalkForwardResults": WalkForwardResults,
            "WalkForwardWindow": WalkForwardWindow,
        }
        return wf_exports[name]

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
