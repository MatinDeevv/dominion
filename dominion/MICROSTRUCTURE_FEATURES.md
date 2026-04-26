# Microstructure Feature Changelog

This changelog lists the `value()` keys added or hardened for the professional microstructure upgrade.

## MicrostructureFeature

| Key | Warmup before non-`None` / non-default | Notes |
| --- | --- | --- |
| `ms_spread` | immediate | Current bid-ask spread. |
| `ms_spread_velocity` | first tick pair | Spread delta per second. |
| `ms_micro_price_divergence` | immediate | Quote-imbalance divergence proxy. |
| `ms_ofi_raw` | immediate | Raw per-tick OFI. |
| `ms_ofi` | immediate | Rolling-window OFI aggregate. |
| `ms_ofi_zscore_100` | 100 ticks | Rolling 100-tick OFI z-score. |
| `ms_ofi_zscore_500` | 500 ticks | Rolling 500-tick OFI z-score. |
| `ms_ofi_normalized` | 100 ticks | Alias of `ms_ofi_zscore_100`. |
| `ms_vpin` | first completed VPIN bucket | Rolling VPIN from completed buckets. |
| `ms_vpin_bucket_volume` | immediate | Current auto-sized VPIN bucket target volume. |
| `ms_vpin_buckets_completed` | first completed VPIN bucket | Total completed VPIN buckets. |
| `ms_tick_entropy` | immediate | Normalized entropy over recent tick directions. |
| `ms_hawkes_buy_intensity` | immediate | Incremental buy-side Hawkes intensity. |
| `ms_hawkes_sell_intensity` | immediate | Incremental sell-side Hawkes intensity. |
| `ms_hawkes_imbalance` | immediate | Intensity imbalance in `[-1, 1]`. |
| `ms_kyles_lambda` | 2 ticks | Impact coefficient on rolling tick changes. |
| `ms_amihud_illiquidity` | 2 ticks | Return-per-volume illiquidity proxy. |
| `ms_roll_spread` | 3 ticks | Roll effective spread estimate. |
| `ms_tsrv` | first fast/slow return pair | Two-scale realized variance estimate. |
| `ms_toxicity` | immediate | Composite toxicity index. |
| `ms_implied_vol` | first tick carrying `implied_vol` | Last seen implied vol snapshot. |
| `ms_vrp` | first tick carrying `implied_vol` plus available `realized_vol_gk` | Vol risk premium. |
| `ms_fractal_dimension` | 64 bars | Higuchi fractal dimension from bar closes. |
| `ms_tick_run_length` | first tick | Current directional run length. |
| `ms_tick_run_direction` | first directional move | `1` up, `-1` down, `0` neutral. |
| `ms_bounce_rate_64` | 64 ticks | Bid-ask bounce / alternation rate. |
| `ms_tick_rate_current` | immediate | Ticks observed in the current second bucket. |
| `ms_quote_stuffing_flag` | 100 completed per-second buckets | Quote-stuffing spike detector. |

Backward-compatible unprefixed aliases remain available inside `MicrostructureFeature.value()`.

## TechnicalFeature

| Key | Warmup before non-`None` / non-default | Notes |
| --- | --- | --- |
| `realized_vol_gk` | configured realized-vol window | Garman-Klass realized volatility. |
| `realized_vol_yz` | configured realized-vol window plus one prior close | Yang-Zhang realized volatility. |
| `realized_vol_pk` | configured realized-vol window | Parkinson realized volatility. |
| `tsrv` | first fast/slow return pair | Bar-level TSRV exposed for vol bundle. |
| `realized_volatility` | same as contained keys | Unified vol dictionary with `gk`, `yz`, `pk`, `tsrv`. |

## RegimeStateFeature

| Key | Warmup before non-`None` / non-default | Notes |
| --- | --- | --- |
| `hurst_exponent` | 100 bars | R/S-analysis Hurst exponent, neutral `0.5` during warmup. |
