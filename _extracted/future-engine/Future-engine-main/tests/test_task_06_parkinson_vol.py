from __future__ import annotations

import pytest

from tests.task_helpers import build_technical_feature, make_bar


def test_realized_volatility_subdict_contains_all_estimators() -> None:
    feature = build_technical_feature(period=20)
    for idx in range(1, 26):
        open_price = 100.0 + idx * 0.7
        feature.on_bar(
            make_bar(
                idx,
                idx * 1_000_000_000,
                open_price=open_price,
                high=open_price + 1.5,
                low=open_price - 1.2,
                close=open_price + 0.6,
            )
        )
    payload = feature.value()["realized_volatility"]
    assert payload is not None
    assert payload["gk"] is not None and payload["gk"] > 0.0
    assert payload["yz"] is not None and payload["yz"] > 0.0
    assert payload["pk"] is not None and payload["pk"] > 0.0
    assert payload["tsrv"] is not None and payload["tsrv"] > 0.0


def test_realized_vol_estimators_are_zero_for_constant_price_series() -> None:
    feature = build_technical_feature(period=20)
    for idx in range(1, 26):
        feature.on_bar(make_bar(idx, idx * 1_000_000_000, open_price=100.0, high=100.0, low=100.0, close=100.0))
    payload = feature.value()["realized_volatility"]
    assert payload["gk"] == pytest.approx(0.0, abs=1e-12)
    assert payload["yz"] == pytest.approx(0.0, abs=1e-12)
    assert payload["pk"] == pytest.approx(0.0, abs=1e-12)
    assert payload["tsrv"] == pytest.approx(0.0, abs=1e-12)
