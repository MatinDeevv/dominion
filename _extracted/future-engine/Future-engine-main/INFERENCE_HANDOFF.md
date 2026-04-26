# Inference Handoff

## Added Now

- `aphelion.inference.feature_schema`: stable 99-dimensional preprocessing contract
- `aphelion.inference.events.FeatureEvent`: snapshot wrapper with `to_numpy()`
- tests for ordering, null handling, alias normalization, and vector conversion

## Current Contract

- numeric features: `90`
- boolean features: `14`
- categorical one-hot features: `3`
- total `FEATURE_DIM`: `107`

The original message's arithmetic was inconsistent with its own explicit field list. The declared feature names resolve to `90 + 14 + 3 = 107`, so the code follows the field list rather than the stale `99` comment.

## Notes For Dan / Integration

1. Microstructure is implemented in the engine, but it is a tick feature family. It is not present in bar-only inference snapshots unless the inference path is fed tick-driven snapshots. When that gets promoted into the inference contract, add the new field names to `NUMERIC_FEATURES` and retrain without changing handler code.
2. The inference contract already omits the redundant `3 x 3` regime transition matrix. Only the three regime probabilities plus regime duration are encoded.
3. Null handling is explicit but still semantically imperfect for price-level fields. We currently fill missing order-block/FVG values with `0.0`. A cleaner next step is to add companion existence booleans such as `market_structure_has_bullish_order_block`.

## Normalization Choices

- engine `market_structure.trend = "neutral"` is normalized to inference `"sideways"`
- session-scoped VWAP anchors like `session_asian` are normalized into the stable `session_open` contract keys
- the note's `volume_profile_volume_imbalance_score` slot is normalized from the engine's `market_structure_volume_imbalance_score`
