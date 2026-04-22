from __future__ import annotations

import numpy as np
import pandas as pd

from aphelion.gold_feature_pack_extra import add_more_high_value_gold_features

EPS = 1e-10


def feat_asian_range(df: pd.DataFrame) -> pd.DataFrame:
    idx = pd.DatetimeIndex(df.index)
    idx_utc = idx.tz_convert("UTC") if idx.tz is not None else idx
    day_key = pd.Series(idx_utc.normalize(), index=df.index)
    asian_mask = idx_utc.hour < 8
    asian_high_running = df["high"].where(asian_mask).groupby(day_key).cummax()
    asian_low_running = df["low"].where(asian_mask).groupby(day_key).cummin()
    asian_high_final = asian_high_running.groupby(day_key).transform("last")
    asian_low_final = asian_low_running.groupby(day_key).transform("last")
    asian_high = asian_high_running.where(asian_mask, asian_high_final).astype(np.float64)
    asian_low = asian_low_running.where(asian_mask, asian_low_final).astype(np.float64)
    close = df["close"].astype(np.float64)
    prev_close = close.shift(1)

    df["asian_high"] = asian_high
    df["asian_low"] = asian_low
    df["asian_range"] = asian_high - asian_low
    df["asian_range_pct"] = (asian_high - asian_low) / (close + EPS) * 100
    df["above_asian_high"] = (close > asian_high).astype(float)
    df["below_asian_low"] = (close < asian_low).astype(float)
    df["inside_asian_range"] = ((close <= asian_high) & (close >= asian_low)).astype(float)
    df["dist_asian_high"] = (asian_high - close) / (close + EPS) * 100
    df["dist_asian_low"] = (close - asian_low) / (close + EPS) * 100
    df["asian_breakout_up"] = ((close > asian_high) & (prev_close <= asian_high)).astype(float)
    df["asian_breakout_dn"] = ((close < asian_low) & (prev_close >= asian_low)).astype(float)
    return df


def feat_previous_levels(df: pd.DataFrame) -> pd.DataFrame:
    idx = pd.DatetimeIndex(df.index)
    idx_utc = idx.tz_convert("UTC") if idx.tz is not None else idx
    idx_naive = idx_utc.tz_localize(None) if idx_utc.tz is not None else idx_utc

    day_key = pd.Series(idx_utc.normalize(), index=df.index)
    day_stats = df.groupby(day_key).agg(
        pdh=("high", "max"),
        pdl=("low", "min"),
        pdc=("close", "last"),
    ).shift(1)

    iso = idx_naive.isocalendar()
    week_key = pd.Series(
        iso["year"].astype(str) + "-W" + iso["week"].astype(str).str.zfill(2),
        index=df.index,
    )
    week_stats = df.groupby(week_key).agg(
        pwh=("high", "max"),
        pwl=("low", "min"),
    ).shift(1)

    month_key = pd.Series(idx_naive.to_period("M").astype(str), index=df.index)
    month_stats = df.groupby(month_key).agg(
        pmh=("high", "max"),
        pml=("low", "min"),
    ).shift(1)

    close = df["close"].astype(np.float64)
    pdh = day_key.map(day_stats["pdh"]).astype(np.float64)
    pdl = day_key.map(day_stats["pdl"]).astype(np.float64)
    pdc = day_key.map(day_stats["pdc"]).astype(np.float64)
    pwh = week_key.map(week_stats["pwh"]).astype(np.float64)
    pwl = week_key.map(week_stats["pwl"]).astype(np.float64)
    pmh = month_key.map(month_stats["pmh"]).astype(np.float64)
    pml = month_key.map(month_stats["pml"]).astype(np.float64)

    df["pdh"] = pdh
    df["pdl"] = pdl
    df["pdc"] = pdc
    df["pwh"] = pwh
    df["pwl"] = pwl
    df["pmh"] = pmh
    df["pml"] = pml
    df["dist_pdh"] = (pdh - close) / (close + EPS) * 100
    df["dist_pdl"] = (close - pdl) / (close + EPS) * 100
    df["dist_pwh"] = (pwh - close) / (close + EPS) * 100
    df["dist_pwl"] = (close - pwl) / (close + EPS) * 100
    df["dist_pmh"] = (pmh - close) / (close + EPS) * 100
    df["dist_pml"] = (close - pml) / (close + EPS) * 100
    df["above_pdh"] = (close > pdh).astype(float)
    df["below_pdl"] = (close < pdl).astype(float)
    df["above_pwh"] = (close > pwh).astype(float)
    df["below_pwl"] = (close < pwl).astype(float)
    return df


def feat_liquidity_sweeps(df: pd.DataFrame) -> pd.DataFrame:
    low = df["low"].astype(np.float64)
    high = df["high"].astype(np.float64)
    close = df["close"].astype(np.float64)

    bull_sweep = pd.Series(False, index=df.index)
    bear_sweep = pd.Series(False, index=df.index)
    for period in [5, 10, 20]:
        prior_low = low.rolling(period, min_periods=period).min().shift(1)
        prior_high = high.rolling(period, min_periods=period).max().shift(1)
        bull_sweep |= (low < prior_low) & (close > prior_low)
        bear_sweep |= (high > prior_high) & (close < prior_high)

    ref_low = low.rolling(20, min_periods=20).min().shift(1)
    ref_high = high.rolling(20, min_periods=20).max().shift(1)
    sweep_size = pd.Series(0.0, index=df.index, dtype=np.float64)
    bull_mask = bull_sweep & ref_low.notna()
    bear_mask = bear_sweep & ref_high.notna()
    sweep_size.loc[bull_mask] = ((ref_low[bull_mask] - low[bull_mask]) / (close[bull_mask] + EPS) * 100).values
    sweep_size.loc[bear_mask] = ((high[bear_mask] - ref_high[bear_mask]) / (close[bear_mask] + EPS) * 100).values

    any_sweep = (bull_sweep | bear_sweep).astype(float)
    df["bull_liq_sweep"] = bull_sweep.astype(float)
    df["bear_liq_sweep"] = bear_sweep.astype(float)
    df["any_liq_sweep"] = any_sweep
    df["sweep_size_pct"] = sweep_size.values
    for period in [20, 50]:
        df[f"sweep_count_{period}"] = any_sweep.rolling(period, min_periods=1).sum().shift(1).fillna(0.0)
    return df


def feat_dxy_beta(df: pd.DataFrame) -> pd.DataFrame:
    dxy_col = None
    for candidate in ["usdx_m5_close", "usdx_h1_close", "usdx_m15_close", "dxy_m5_close", "dxy_h1_close"]:
        if candidate in df.columns:
            dxy_col = candidate
            break
    if dxy_col is None:
        return df

    gold = pd.Series(df["close"].astype(np.float64).values, index=df.index)
    dxy = pd.Series(df[dxy_col].astype(np.float64).values, index=df.index).replace(0.0, np.nan)
    gold_ret = gold.pct_change(fill_method=None).fillna(0.0)
    dxy_ret = dxy.pct_change(fill_method=None)

    for period in [20, 60, 240]:
        min_obs = max(5, period // 2)
        beta = gold_ret.rolling(period, min_periods=min_obs).cov(dxy_ret) / (
            dxy_ret.rolling(period, min_periods=min_obs).var() + EPS
        )
        corr = gold_ret.rolling(period, min_periods=min_obs).corr(dxy_ret)
        df[f"dxy_beta_{period}"] = beta.values
        df[f"dxy_corr_{period}"] = corr.values
        df[f"dxy_corr_negative_{period}"] = (corr.fillna(0.0) < -0.5).astype(float).values
        df[f"dxy_corr_broken_{period}"] = (corr.fillna(0.0) > 0.0).astype(float).values
    return df


def feat_order_blocks(df: pd.DataFrame) -> pd.DataFrame:
    high = df["high"].values.astype(np.float64)
    low = df["low"].values.astype(np.float64)
    close = df["close"].values.astype(np.float64)
    open_ = df["open"].values.astype(np.float64)
    n_rows = len(df)

    bull_ob = np.zeros(n_rows, dtype=np.float64)
    bear_ob = np.zeros(n_rows, dtype=np.float64)
    dist_bull = np.full(n_rows, np.nan, dtype=np.float64)
    dist_bear = np.full(n_rows, np.nan, dtype=np.float64)
    displacement_threshold = 0.003

    for index in range(3, n_rows):
        if close[index - 1] < open_[index - 1]:
            move = (close[index] - open_[index]) / (open_[index] + EPS)
            if move > displacement_threshold:
                bull_ob[index - 1] = 1.0
        if close[index - 1] > open_[index - 1]:
            move = (open_[index] - close[index]) / (open_[index] + EPS)
            if move > displacement_threshold:
                bear_ob[index - 1] = 1.0

    bull_levels: list[float] = []
    bear_levels: list[float] = []
    for index in range(n_rows):
        if bull_ob[index]:
            bull_levels.append((low[index] + high[index]) / 2.0)
        if bear_ob[index]:
            bear_levels.append((low[index] + high[index]) / 2.0)
        bull_levels = bull_levels[-10:]
        bear_levels = bear_levels[-10:]
        if bull_levels:
            dist_bull[index] = min(abs(close[index] - level) / (close[index] + EPS) * 100 for level in bull_levels)
        if bear_levels:
            dist_bear[index] = min(abs(close[index] - level) / (close[index] + EPS) * 100 for level in bear_levels)

    df["bull_ob"] = bull_ob
    df["bear_ob"] = bear_ob
    df["dist_bull_ob"] = dist_bull
    df["dist_bear_ob"] = dist_bear
    df["near_bull_ob"] = (np.nan_to_num(dist_bull) < 0.2).astype(float)
    df["near_bear_ob"] = (np.nan_to_num(dist_bear) < 0.2).astype(float)
    return df


def feat_displacement(df: pd.DataFrame) -> pd.DataFrame:
    close = df["close"].values.astype(np.float64)
    open_ = df["open"].values.astype(np.float64)
    high = df["high"].values.astype(np.float64)
    low = df["low"].values.astype(np.float64)
    n_rows = len(df)

    body = np.abs(close - open_)
    range_size = high - low
    body_pct = body / (range_size + EPS)
    prev_close = np.roll(close, 1)
    prev_close[0] = close[0]
    tr = np.maximum(high - low, np.maximum(np.abs(high - prev_close), np.abs(low - prev_close)))
    atr = np.zeros(n_rows, dtype=np.float64)
    atr[0] = tr[0]
    for index in range(1, n_rows):
        atr[index] = 0.9 * atr[index - 1] + 0.1 * tr[index]

    displacement_up = ((body > 2 * atr) & (body_pct > 0.7) & (close > open_)).astype(float)
    displacement_dn = ((body > 2 * atr) & (body_pct > 0.7) & (close < open_)).astype(float)
    df["displacement_up"] = displacement_up
    df["displacement_dn"] = displacement_dn
    df["displacement_any"] = np.maximum(displacement_up, displacement_dn)
    df["displacement_size"] = body / (atr + EPS)

    bars_since = np.full(n_rows, 999.0, dtype=np.float64)
    last_seen = 999
    last_dir = 0.0
    last_disp_dir = np.zeros(n_rows, dtype=np.float64)
    for index in range(n_rows):
        if displacement_up[index] or displacement_dn[index]:
            last_seen = 0
            last_dir = 1.0 if displacement_up[index] else -1.0
        bars_since[index] = last_seen
        last_seen += 1
        last_disp_dir[index] = last_dir
    df["bars_since_displacement"] = np.minimum(bars_since, 100.0)
    df["last_displacement_dir"] = last_disp_dir
    return df


def feat_silver_relationship(df: pd.DataFrame) -> pd.DataFrame:
    ag_col = None
    for candidate in ["xagusd_m5_close", "xagusd_m15_close", "xagusd_h1_close"]:
        if candidate in df.columns:
            ag_col = candidate
            break
    if ag_col is None:
        return df

    close = pd.Series(df["close"].astype(np.float64).values, index=df.index)
    silver = pd.Series(df[ag_col].astype(np.float64).values, index=df.index).replace(0.0, np.nan)
    ratio = close / (silver + EPS)
    df["gold_silver_ratio"] = ratio.values

    for period in [20, 60]:
        ratio_mean = ratio.rolling(period, min_periods=max(5, period // 2)).mean()
        ratio_std = ratio.rolling(period, min_periods=max(5, period // 2)).std(ddof=0)
        zscore = (ratio - ratio_mean) / (ratio_std + EPS)
        df[f"gs_ratio_zscore_{period}"] = zscore.values
        df[f"gs_ratio_high_{period}"] = (zscore.fillna(0.0) > 1.0).astype(float).values
        df[f"gs_ratio_low_{period}"] = (zscore.fillna(0.0) < -1.0).astype(float).values

    gold_ret = close.pct_change(fill_method=None).fillna(0.0).values
    silver_ret = silver.pct_change(fill_method=None).fillna(0.0).values
    for lag in [1, 2, 3, 5]:
        silver_lead = np.roll(silver_ret, lag)
        silver_lead[:lag] = 0.0
        df[f"ag_lead_{lag}_agree"] = (np.sign(silver_lead) == np.sign(gold_ret)).astype(float)
    return df


def feat_spread_anomaly(df: pd.DataFrame) -> pd.DataFrame:
    spread_col = None
    for candidate in ["spread_mean", "spread", "xau_m1_spread"]:
        if candidate in df.columns:
            spread_col = candidate
            break
    if spread_col is None:
        return df

    spread = pd.Series(df[spread_col].astype(np.float64).values, index=df.index).replace(0.0, np.nan)
    for period in [20, 100, 1440]:
        spread_mean = spread.rolling(period, min_periods=max(5, period // 2)).mean()
        spread_std = spread.rolling(period, min_periods=max(5, period // 2)).std(ddof=0)
        spread_z = (spread - spread_mean) / (spread_std + EPS)
        df[f"spread_zscore_{period}"] = spread_z.fillna(0.0).values
        df[f"spread_elevated_{period}"] = (spread_z.fillna(0.0) > 2.0).astype(float).values
        df[f"spread_danger_{period}"] = (spread_z.fillna(0.0) > 4.0).astype(float).values

    if "atr_14" in df.columns:
        atr = pd.Series(df["atr_14"].astype(np.float64).values, index=df.index)
        spread_vs_atr = spread.fillna(0.0) / (atr + EPS)
        df["spread_vs_atr"] = spread_vs_atr.values
        df["bad_spread"] = (spread_vs_atr > 0.3).astype(float).values
    return df


def feat_mtf_confluence(df: pd.DataFrame) -> pd.DataFrame:
    close = df["close"].values.astype(np.float64)
    n_rows = len(df)
    tf_signals: dict[str, np.ndarray] = {}
    htf_cols = {
        "m5": "xau_m5_close",
        "m15": "xau_m15_close",
        "h1": "xau_h1_close",
        "h4": "xau_h4_close",
        "d1": "xau_d1_close",
    }

    for tf_name, col in htf_cols.items():
        if col not in df.columns:
            continue
        htf_close = np.nan_to_num(df[col].values.astype(np.float64))
        if len(htf_close) != n_rows:
            continue
        htf_ema = np.zeros(n_rows, dtype=np.float64)
        htf_ema[0] = htf_close[0]
        for index in range(1, n_rows):
            htf_ema[index] = 0.095 * htf_close[index] + 0.905 * htf_ema[index - 1]
        above = (close > htf_ema).astype(float)
        below = (close < htf_ema).astype(float)
        tf_signals[tf_name] = above - below
        df[f"mtf_{tf_name}_bull"] = above
        df[f"mtf_{tf_name}_bear"] = below

    if tf_signals:
        stack = np.column_stack(list(tf_signals.values()))
        df["mtf_bull_count"] = np.sum(stack > 0, axis=1)
        df["mtf_bear_count"] = np.sum(stack < 0, axis=1)
        df["mtf_score"] = np.mean(stack, axis=1)
        df["mtf_full_bull"] = (df["mtf_bull_count"] == stack.shape[1]).astype(float)
        df["mtf_full_bear"] = (df["mtf_bear_count"] == stack.shape[1]).astype(float)
        df["mtf_conflict"] = ((df["mtf_bull_count"] > 0) & (df["mtf_bear_count"] > 0)).astype(float)
    return df


def feat_macro_timing(df: pd.DataFrame) -> pd.DataFrame:
    idx = pd.DatetimeIndex(df.index)
    idx_utc = idx.tz_convert("UTC") if idx.tz is not None else idx
    hours = idx_utc.hour
    minutes = idx_utc.minute
    day_of_week = idx_utc.dayofweek
    day_of_month = idx_utc.day

    is_first_friday = (day_of_month <= 7) & (day_of_week == 4)
    nfp_window = is_first_friday & (hours == 13)
    is_second_week = (day_of_month >= 8) & (day_of_month <= 14)
    is_tue_wed = (day_of_week == 1) | (day_of_week == 2)
    cpi_window = is_second_week & is_tue_wed & (hours == 13)
    fed_window = (day_of_week == 2) & (hours >= 18) & (hours <= 20)
    us_open_danger = (hours == 13) & (minutes >= 15) & (minutes <= 45)
    london_open_vol = (hours == 7) | ((hours == 8) & (minutes <= 30))

    minutes_in_day = hours * 60 + minutes
    us_open_minutes = 13 * 60 + 30
    minutes_to_open = (us_open_minutes - minutes_in_day) % (24 * 60)

    df["nfp_window"] = nfp_window.astype(int)
    df["nfp_day"] = is_first_friday.astype(int)
    df["cpi_window"] = cpi_window.astype(int)
    df["fed_window"] = fed_window.astype(int)
    df["us_open_danger"] = us_open_danger.astype(int)
    df["london_open_vol"] = london_open_vol.astype(int)
    df["high_impact_news"] = (nfp_window | cpi_window | fed_window).astype(int)
    df["avoid_trading"] = (nfp_window | cpi_window).astype(int)
    df["mins_to_us_open"] = np.minimum(minutes_to_open, 240)
    return df


def add_high_value_gold_features(df: pd.DataFrame) -> pd.DataFrame:
    df = feat_asian_range(df)
    df = feat_previous_levels(df)
    df = feat_liquidity_sweeps(df)
    df = feat_dxy_beta(df)
    df = feat_order_blocks(df)
    df = feat_displacement(df)
    df = feat_silver_relationship(df)
    df = feat_spread_anomaly(df)
    df = feat_mtf_confluence(df)
    df = feat_macro_timing(df)
    df = add_more_high_value_gold_features(df)
    return df.copy()


__all__ = [
    "add_high_value_gold_features",
    "feat_asian_range",
    "feat_previous_levels",
    "feat_liquidity_sweeps",
    "feat_dxy_beta",
    "feat_order_blocks",
    "feat_displacement",
    "feat_silver_relationship",
    "feat_spread_anomaly",
    "feat_mtf_confluence",
    "feat_macro_timing",
]
