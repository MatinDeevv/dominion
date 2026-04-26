from __future__ import annotations

from collections import deque
from typing import Any, Sequence

from ..events import CrossAssetAlignedEvent
from ..utils import correlation, covariance, log_return, mean, safe_div, stddev
from .base import CrossAssetFeature, FeatureContext


def compute_cointegration_zscores(primary_prices: Sequence[float], other_prices: Sequence[float]) -> float:
    if len(primary_prices) < 3 or len(primary_prices) != len(other_prices):
        return 0.0
    beta = safe_div(covariance(primary_prices, other_prices), max(stddev(list(other_prices)) ** 2, 1e-9))
    spread = [primary - (beta * other) for primary, other in zip(primary_prices, other_prices)]
    spread_mean = mean(spread)
    spread_std = stddev(spread)
    return safe_div(spread[-1] - spread_mean, spread_std)


def compute_rolling_correlations(primary_returns: Sequence[float], other_returns: Sequence[float]) -> float:
    return correlation(list(primary_returns), list(other_returns))


def _compute_beta(primary_returns: Sequence[float], other_returns: Sequence[float]) -> float:
    return safe_div(covariance(primary_returns, other_returns), max(stddev(list(other_returns)) ** 2, 1e-9))


def compute_beta_to_dxy(primary_returns: Sequence[float], other_returns: Sequence[float]) -> float:
    return _compute_beta(primary_returns, other_returns)


def compute_beta_to_spx(primary_returns: Sequence[float], other_returns: Sequence[float]) -> float:
    return _compute_beta(primary_returns, other_returns)


def compute_beta_to_yields(primary_returns: Sequence[float], other_returns: Sequence[float]) -> float:
    return _compute_beta(primary_returns, other_returns)


def compute_relative_strength_vs_commodity_complex(primary_returns: Sequence[float], basket_returns: Sequence[float]) -> float:
    return sum(primary_returns) - sum(basket_returns)


class CrossAssetRelationshipFeature(CrossAssetFeature):
    def __init__(
        self,
        *,
        name: str = "cross_asset",
        version: str = "1.0.0",
        primary_symbol: str = "XAUUSD",
        relationships: dict[str, str] | None = None,
        commodity_basket: tuple[str, ...] = ("XAGUSD",),
        include_btc: bool = False,
        day_windows: tuple[int, ...] = (30, 60, 90),
        bars_per_day: int = 24,
        default_timeframe: str = "1h",
    ) -> None:
        relationships = dict(relationships or {"dxy": "DXY", "real_yields": "US10Y_REAL", "silver": "XAGUSD", "spx": "SPX"})
        if include_btc:
            relationships["btc"] = "BTCUSD"
        required_symbols = {primary_symbol, *relationships.values(), *commodity_basket}
        super().__init__(
            name=name,
            version=version,
            default_timeframe=default_timeframe,
            warmup_periods=max(day_windows) * bars_per_day,
            required_symbols=required_symbols,
        )
        self.primary_symbol = primary_symbol
        self.relationships = relationships
        self.commodity_basket = commodity_basket
        self.day_windows = day_windows
        self.bars_per_day = bars_per_day
        self.window_bars = {window: window * bars_per_day for window in day_windows}
        self.max_window = max(self.window_bars.values()) + 1

    def initialize_state(self) -> dict[str, Any]:
        symbols = self.required_symbols
        return {
            "prices": {symbol: deque(maxlen=self.max_window) for symbol in symbols},
            "returns": {symbol: deque(maxlen=self.max_window) for symbol in symbols},
            "values": {},
        }

    def update(self, event: CrossAssetAlignedEvent, state: dict[str, Any], context: FeatureContext) -> None:
        if not isinstance(event, CrossAssetAlignedEvent):
            return

        for symbol, bar in event.bars.items():
            prices = state["prices"][symbol]
            previous = prices[-1] if prices else None
            prices.append(bar.close)
            if previous is not None:
                state["returns"][symbol].append(log_return(bar.close, previous))

        payload: dict[str, Any] = {}
        primary_prices_all = list(state["prices"][self.primary_symbol])
        primary_returns_all = list(state["returns"][self.primary_symbol])

        for label, symbol in self.relationships.items():
            other_prices_all = list(state["prices"][symbol])
            other_returns_all = list(state["returns"][symbol])
            relation_payload: dict[str, Any] = {}
            for window, bars in self.window_bars.items():
                primary_prices = primary_prices_all[-bars:]
                other_prices = other_prices_all[-bars:]
                primary_returns = primary_returns_all[-bars:]
                other_returns = other_returns_all[-bars:]
                relation_payload[f"{window}d_corr"] = compute_rolling_correlations(primary_returns, other_returns)
                relation_payload[f"{window}d_coint_z"] = compute_cointegration_zscores(primary_prices, other_prices)
                if label == "dxy":
                    relation_payload[f"{window}d_beta"] = compute_beta_to_dxy(primary_returns, other_returns)
                elif label == "spx":
                    relation_payload[f"{window}d_beta"] = compute_beta_to_spx(primary_returns, other_returns)
                elif label == "real_yields":
                    relation_payload[f"{window}d_beta"] = compute_beta_to_yields(primary_returns, other_returns)
                else:
                    relation_payload[f"{window}d_beta"] = _compute_beta(primary_returns, other_returns)
            payload[label] = relation_payload

        if self.commodity_basket:
            basket_returns = []
            for window, bars in self.window_bars.items():
                basket_series = []
                for symbol in self.commodity_basket:
                    returns_series = list(state["returns"][symbol])[-bars:]
                    if returns_series:
                        basket_series.append(sum(returns_series) / len(returns_series))
                basket_mean = mean(basket_series) if basket_series else 0.0
                primary_returns = primary_returns_all[-bars:]
                basket_returns.append(
                    {
                        f"{window}d_relative_strength": compute_relative_strength_vs_commodity_complex(
                            primary_returns,
                            [basket_mean] * len(primary_returns),
                        )
                    }
                )
            payload["commodity_complex"] = {
                key: value for item in basket_returns for key, value in item.items()
            }

        state["values"] = payload

    def ready(self, state: dict[str, Any]) -> bool:
        return len(state["prices"][self.primary_symbol]) >= min(self.max_window, self.warmup_periods)

    def value(self, state: dict[str, Any]) -> dict[str, Any]:
        return dict(state["values"])

