from __future__ import annotations

import math

import pytest

from tests.task_helpers import build_technical_feature, make_bar


def test_realized_vol_gk_matches_manual_reference() -> None:
    feature = build_technical_feature(period=3)
    bars = [
        make_bar(1, 1_000_000_000, open_price=100.0, high=103.0, low=99.0, close=102.0),
        make_bar(2, 2_000_000_000, open_price=102.0, high=104.0, low=101.0, close=103.0),
        make_bar(3, 3_000_000_000, open_price=103.0, high=106.0, low=102.0, close=105.0),
    ]
    for bar in bars:
        feature.on_bar(bar)
    expected_terms = []
    for bar in bars:
        hl = math.log(bar.high / bar.low)
        oc = math.log(bar.close / bar.open)
        expected_terms.append(0.5 * (hl**2) - ((2.0 * math.log(2.0)) - 1.0) * (oc**2))
    expected = math.sqrt(sum(expected_terms) / 3.0)
    assert feature.value()["realized_vol_gk"] == pytest.approx(expected, abs=1e-6)


def test_realized_vol_gk_is_none_before_window_is_full() -> None:
    feature = build_technical_feature(period=20)
    for idx in range(1, 6):
        feature.on_bar(make_bar(idx, idx * 1_000_000_000, open_price=100.0 + idx, high=101.0 + idx, low=99.0 + idx, close=100.5 + idx))
    assert feature.value()["realized_vol_gk"] is None


def test_realized_vol_gk_handles_zero_range_bar_without_error() -> None:
    feature = build_technical_feature(period=3)
    bars = [
        make_bar(1, 1_000_000_000, open_price=100.0, high=101.0, low=99.0, close=100.5),
        make_bar(2, 2_000_000_000, open_price=100.5, high=101.5, low=100.0, close=101.0),
        make_bar(3, 3_000_000_000, open_price=101.0, high=101.0, low=101.0, close=101.0),
    ]
    for bar in bars:
        feature.on_bar(bar)
    assert feature.value()["realized_vol_gk"] is not None
