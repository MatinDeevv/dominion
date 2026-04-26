from __future__ import annotations

import math

import numpy as np
import pytest

from tests.task_helpers import build_technical_feature, make_bar


def test_realized_vol_yz_matches_reference_implementation() -> None:
    feature = build_technical_feature(period=20)
    bars = []
    for idx in range(1, 26):
        open_price = 100.0 + idx * 0.8
        high = open_price + 1.5 + (idx % 3) * 0.1
        low = open_price - 1.0 - (idx % 2) * 0.1
        close = open_price + 0.4 + (idx % 4) * 0.05
        bar = make_bar(idx, idx * 1_000_000_000, open_price=open_price, high=high, low=low, close=close)
        bars.append(bar)
        feature.on_bar(bar)

    values = feature.value()
    assert values["realized_vol_yz"] is not None
    assert values["realized_vol_yz"] > 0.0

    gk_terms = []
    overnight = []
    open_close = []
    for prev_bar, bar in zip(bars[-21:-1], bars[-20:]):
        hl = math.log(bar.high / bar.low)
        oc = math.log(bar.close / bar.open)
        gk_terms.append(0.5 * (hl**2) - ((2.0 * math.log(2.0)) - 1.0) * (oc**2))
        overnight.append(math.log(bar.open / prev_bar.close))
        open_close.append(math.log(bar.close / bar.open))
    gk = math.sqrt(sum(gk_terms) / 20.0)
    k = 0.34 / (1.34 + (21 / 19))
    reference = math.sqrt(np.var(overnight, ddof=1) + k * np.var(open_close, ddof=1) + (1.0 - k) * (gk**2))
    assert values["realized_vol_yz"] == pytest.approx(reference, abs=1e-6)


def test_realized_vol_yz_is_none_with_insufficient_history() -> None:
    feature = build_technical_feature(period=20)
    for idx in range(1, 6):
        feature.on_bar(make_bar(idx, idx * 1_000_000_000, open_price=100.0 + idx, high=101.0 + idx, low=99.0 + idx, close=100.5 + idx))
    assert feature.value()["realized_vol_yz"] is None
