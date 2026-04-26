from __future__ import annotations

from typing import Any, Iterable

import numpy as np


# Numeric features: pass through as float.
NUMERIC_FEATURES = [
    "volume_profile_volume_delta",
    "volume_profile_cvd",
    "volume_profile_poc",
    "volume_profile_vah",
    "volume_profile_val",
    "volume_profile_volume_imbalance_score",
    "vwap_session_vwap",
    "vwap_rolling_vwap",
    "vwap_band_up_1",
    "vwap_band_down_1",
    "vwap_band_up_2",
    "vwap_band_down_2",
    "vwap_anchors_session_open_vwap",
    "vwap_anchors_session_open_band_up_1",
    "vwap_anchors_session_open_band_down_1",
    "technical_atr_5",
    "technical_atr_10",
    "technical_atr_14",
    "technical_atr_20",
    "technical_atr_50",
    "technical_bollinger_10_upper",
    "technical_bollinger_10_mid",
    "technical_bollinger_10_lower",
    "technical_bollinger_20_upper",
    "technical_bollinger_20_mid",
    "technical_bollinger_20_lower",
    "technical_bollinger_50_upper",
    "technical_bollinger_50_mid",
    "technical_bollinger_50_lower",
    "technical_rsi_7",
    "technical_rsi_14",
    "technical_rsi_21",
    "technical_macd_line",
    "technical_macd_signal",
    "technical_macd_histogram",
    "technical_ema_5",
    "technical_ema_10",
    "technical_ema_12",
    "technical_ema_20",
    "technical_ema_26",
    "technical_ema_30",
    "technical_ema_40",
    "technical_ema_50",
    "technical_sma_5",
    "technical_sma_10",
    "technical_sma_20",
    "technical_sma_30",
    "technical_sma_40",
    "technical_sma_50",
    "technical_stochastic_14_k",
    "technical_stochastic_14_d",
    "technical_stochastic_21_k",
    "technical_stochastic_21_d",
    "technical_adx_adx",
    "technical_adx_plus_di",
    "technical_adx_minus_di",
    "session_calendar_minutes_to_asian_open",
    "session_calendar_minutes_to_asian_close",
    "session_calendar_minutes_to_london_open",
    "session_calendar_minutes_to_london_close",
    "session_calendar_minutes_to_new_york_open",
    "session_calendar_minutes_to_new_york_close",
    "session_calendar_day_of_week_sin",
    "session_calendar_day_of_week_cos",
    "session_calendar_week_of_month",
    "market_structure_last_swing_high",
    "market_structure_last_swing_low",
    "market_structure_bullish_order_block_low",
    "market_structure_bullish_order_block_high",
    "market_structure_bearish_order_block_low",
    "market_structure_bearish_order_block_high",
    "market_structure_bullish_fvg_low",
    "market_structure_bullish_fvg_high",
    "market_structure_bearish_fvg_low",
    "market_structure_bearish_fvg_high",
    "market_structure_bullish_breaker_count",
    "market_structure_bearish_breaker_count",
    "cross_asset_dxy_5d_corr",
    "cross_asset_dxy_5d_coint_z",
    "cross_asset_dxy_5d_beta",
    "cross_asset_dxy_10d_corr",
    "cross_asset_dxy_10d_coint_z",
    "cross_asset_dxy_10d_beta",
    "cross_asset_dxy_20d_corr",
    "cross_asset_dxy_20d_coint_z",
    "cross_asset_dxy_20d_beta",
    "regime_probabilities_trending",
    "regime_probabilities_mean_reverting",
    "regime_probabilities_volatile",
    "regime_regime_duration",
]

# Boolean features: encode as 0/1 float.
BOOLEAN_FEATURES = [
    "volume_profile_delta_divergence",
    "volume_profile_absorption",
    "session_calendar_asian",
    "session_calendar_london",
    "session_calendar_new_york",
    "session_calendar_london_new_york_overlap",
    "session_calendar_month_end_flag",
    "session_calendar_quarter_end_flag",
    "market_structure_bullish_bos",
    "market_structure_bearish_bos",
    "market_structure_bullish_choch",
    "market_structure_bearish_choch",
    "market_structure_bullish_volume_imbalance",
    "market_structure_bearish_volume_imbalance",
]

# market_structure_trend: "up" | "down" | "sideways"
TREND_ENCODING = {
    "up": [1.0, 0.0, 0.0],
    "down": [0.0, 1.0, 0.0],
    "sideways": [0.0, 0.0, 1.0],
    "neutral": [0.0, 0.0, 1.0],
    None: [0.0, 0.0, 0.0],
}

NULL_FILLS: dict[str, float] = {
    "session_calendar_minutes_to_news": 999.0,
    "market_structure_last_swing_high": 0.0,
    "market_structure_last_swing_low": 0.0,
    "market_structure_bullish_order_block_low": 0.0,
    "market_structure_bullish_order_block_high": 0.0,
    "market_structure_bearish_order_block_low": 0.0,
    "market_structure_bearish_order_block_high": 0.0,
    "market_structure_bullish_fvg_low": 0.0,
    "market_structure_bullish_fvg_high": 0.0,
    "market_structure_bearish_fvg_low": 0.0,
    "market_structure_bearish_fvg_high": 0.0,
}

FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "volume_profile_volume_imbalance_score": ("market_structure_volume_imbalance_score",),
    "vwap_anchors_session_open_vwap": (
        "vwap_anchors_session_asian_vwap",
        "vwap_anchors_session_london_vwap",
        "vwap_anchors_session_new_york_vwap",
    ),
    "vwap_anchors_session_open_band_up_1": (
        "vwap_anchors_session_asian_band_up_1",
        "vwap_anchors_session_london_band_up_1",
        "vwap_anchors_session_new_york_band_up_1",
    ),
    "vwap_anchors_session_open_band_down_1": (
        "vwap_anchors_session_asian_band_down_1",
        "vwap_anchors_session_london_band_down_1",
        "vwap_anchors_session_new_york_band_down_1",
    ),
}

FEATURE_DIM = len(NUMERIC_FEATURES) + len(BOOLEAN_FEATURES) + 3


def flatten_snapshot(features: dict[str, Any]) -> dict[str, Any]:
    """Flatten FeatureSnapshot.features into underscore-delimited keys."""
    result: dict[str, Any] = {}

    def _flatten(obj: Any, prefix: str = "") -> None:
        if isinstance(obj, dict):
            for key, value in obj.items():
                nested_prefix = f"{prefix}{key}_" if prefix else f"{key}_"
                _flatten(value, nested_prefix)
            return
        result[prefix.rstrip("_")] = obj

    _flatten(features)

    # Expose the string trend directly and normalize the engine's "neutral" label.
    trend = features.get("market_structure", {}).get("trend")
    if trend == "neutral":
        trend = "sideways"
    result["market_structure_trend"] = trend

    # Normalize whichever session-scoped anchor the engine emitted into one stable inference slot.
    _ensure_alias_value(result, "vwap_anchors_session_open_vwap")
    _ensure_alias_value(result, "vwap_anchors_session_open_band_up_1")
    _ensure_alias_value(result, "vwap_anchors_session_open_band_down_1")
    _ensure_alias_value(result, "volume_profile_volume_imbalance_score")
    return result


def _ensure_alias_value(flat_features: dict[str, Any], canonical_name: str) -> None:
    if flat_features.get(canonical_name) is not None:
        return
    for alias in FIELD_ALIASES.get(canonical_name, ()):
        if alias in flat_features and flat_features[alias] is not None:
            flat_features[canonical_name] = flat_features[alias]
            return


def resolve_feature(flat_features: dict[str, Any], name: str) -> Any:
    if name in flat_features and flat_features[name] is not None:
        return flat_features[name]
    for alias in FIELD_ALIASES.get(name, ()):
        if alias in flat_features and flat_features[alias] is not None:
            return flat_features[alias]
    if name in flat_features:
        return flat_features[name]
    return None


def snapshot_to_numpy(flat_features: dict[str, Any]) -> np.ndarray:
    """
    Convert a flattened feature dict into the fixed-length float32 model vector.
    """
    vec: list[float] = []

    for name in NUMERIC_FEATURES:
        value = resolve_feature(flat_features, name)
        if value is None:
            value = NULL_FILLS.get(name, 0.0)
        vec.append(float(value))

    for name in BOOLEAN_FEATURES:
        value = resolve_feature(flat_features, name)
        vec.append(1.0 if value else 0.0)

    trend = resolve_feature(flat_features, "market_structure_trend")
    vec.extend(TREND_ENCODING.get(trend, TREND_ENCODING[None]))

    arr = np.asarray(vec, dtype=np.float32)
    assert arr.shape[0] == FEATURE_DIM, f"Expected {FEATURE_DIM} features, got {arr.shape[0]}"
    return arr


def vector_index(name: str) -> int:
    if name in NUMERIC_FEATURES:
        return NUMERIC_FEATURES.index(name)
    boolean_offset = len(NUMERIC_FEATURES)
    if name in BOOLEAN_FEATURES:
        return boolean_offset + BOOLEAN_FEATURES.index(name)
    trend_offset = boolean_offset + len(BOOLEAN_FEATURES)
    if name == "market_structure_trend_up":
        return trend_offset
    if name == "market_structure_trend_down":
        return trend_offset + 1
    if name == "market_structure_trend_sideways":
        return trend_offset + 2
    raise KeyError(name)


def missing_contract_fields(flat_features: dict[str, Any]) -> dict[str, list[str]]:
    numeric_missing = [name for name in NUMERIC_FEATURES if resolve_feature(flat_features, name) is None]
    boolean_missing = [name for name in BOOLEAN_FEATURES if resolve_feature(flat_features, name) is None]
    categorical_missing = [] if resolve_feature(flat_features, "market_structure_trend") is not None else ["market_structure_trend"]
    return {
        "numeric": numeric_missing,
        "boolean": boolean_missing,
        "categorical": categorical_missing,
    }
