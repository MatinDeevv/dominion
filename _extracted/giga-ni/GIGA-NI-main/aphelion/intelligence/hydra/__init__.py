"""
APHELION HYDRA — Neural Intelligence Core (Phase 4+7: Full Ensemble)
TFT + LSTM + CNN + MoE ensemble for multi-horizon XAU/USD direction prediction.

Export policy:
  - If PyTorch is installed: all model, dataset, trainer, inference, and strategy
    classes are exported.  ``HAS_TORCH`` is ``True``.
  - If PyTorch is *not* installed: only ``HAS_TORCH = False`` is exported and a
    clear warning is emitted so callers know *why* the module is inert.
  - Any unexpected import error (broken install, version mismatch) is logged at
    WARNING level rather than silently swallowed, so developers can diagnose it.
"""

from __future__ import annotations

import logging as _logging

_logger = _logging.getLogger(__name__)
_IMPORT_ERROR: Exception | None = None
_UNAVAILABLE_REASON = ""
_HYDRA_EXPORTS = [
    # Models
    "TemporalFusionTransformer", "TFTConfig",
    "HydraLSTM", "LSTMConfig",
    "HydraCNN", "CNNConfig",
    "HydraMoE", "MoEConfig",
    "HydraTCN", "TCNConfig",
    "HydraTransformer", "TransformerConfig",
    "HydraGate", "EnsembleConfig",
    # Tree models
    "HydraXGBoost", "HydraRandomForest", "HydraTreeEnsemble",
    "TreeModelConfig", "TreePrediction",
    # Calibration & Disagreement
    "IsotonicCalibrator", "DisagreementDetector",
    "DynamicEnsembleWeights", "CalibrationResult",
    # Adversarial robustness
    "AdversarialConfig", "AdversarialAssessment", "AdversarialFeaturePerturbationDetector",
    # Data
    "HydraDataset", "DatasetConfig",
    "create_dataloaders", "build_dataset_from_feature_dicts",
    "CONTINUOUS_FEATURES", "CATEGORICAL_FEATURES",
    # Training
    "HydraTrainer", "TrainerConfig",
    # Inference & Strategy
    "HydraInference", "InferenceConfig", "HydraSignal",
    "HydraStrategy", "StrategyConfig",
    # Online Learning
    "OnlineLearner", "OnlineConfig", "OnlineStats", "OnlineExperience",
]

# ── Attempt to import the full HYDRA API ──────────────────────────────────

try:
    from aphelion.intelligence.hydra.tft import (
        TemporalFusionTransformer,
        TFTConfig,
    )
    from aphelion.intelligence.hydra.lstm import HydraLSTM, LSTMConfig
    from aphelion.intelligence.hydra.cnn import HydraCNN, CNNConfig
    from aphelion.intelligence.hydra.moe import HydraMoE, MoEConfig
    from aphelion.intelligence.hydra.tcn import HydraTCN, TCNConfig
    from aphelion.intelligence.hydra.transformer import HydraTransformer, TransformerConfig
    from aphelion.intelligence.hydra.ensemble import HydraGate, EnsembleConfig

    from aphelion.intelligence.hydra.dataset import (
        HydraDataset,
        DatasetConfig,
        create_dataloaders,
        build_dataset_from_feature_dicts,
        CONTINUOUS_FEATURES,
        CATEGORICAL_FEATURES,
    )
    from aphelion.intelligence.hydra.trainer import (
        HydraTrainer,
        TrainerConfig,
    )
    from aphelion.intelligence.hydra.inference import (
        HydraInference,
        InferenceConfig,
        HydraSignal,
    )
    from aphelion.intelligence.hydra.strategy import (
        HydraStrategy,
        StrategyConfig,
    )
    from aphelion.intelligence.hydra.online import (
        OnlineLearner,
        OnlineConfig,
        OnlineStats,
        OnlineExperience,
    )
    from aphelion.intelligence.hydra.calibration import (
        IsotonicCalibrator,
        DisagreementDetector,
        DynamicEnsembleWeights,
        CalibrationResult,
    )
    from aphelion.intelligence.hydra.adversarial import (
        AdversarialConfig,
        AdversarialAssessment,
        AdversarialFeaturePerturbationDetector,
    )
    from aphelion.intelligence.hydra.xgb_model import (
        HydraXGBoost,
        HydraRandomForest,
        HydraTreeEnsemble,
        TreeModelConfig,
        TreePrediction,
    )

    HAS_TORCH = True

    __all__ = [*_HYDRA_EXPORTS, "HAS_TORCH"]

except ModuleNotFoundError as _exc:
    HAS_TORCH = False
    __all__ = ["HAS_TORCH"]
    _IMPORT_ERROR = _exc
    missing_root = (_exc.name or "").split(".")[0]
    if missing_root == "torch":
        _UNAVAILABLE_REASON = "PyTorch not installed"
        _logger.debug(
            "PyTorch not installed — HYDRA module inert. "
            "Install with: pip install -e '.[ml]'"
        )
    else:
        _UNAVAILABLE_REASON = f"missing optional dependency '{_exc.name}'"
        _logger.warning(
            "HYDRA import failed because dependency %r is missing.",
            _exc.name,
            exc_info=True,
        )

except Exception as _exc:
    HAS_TORCH = False
    __all__ = ["HAS_TORCH"]
    _IMPORT_ERROR = _exc
    _UNAVAILABLE_REASON = "unexpected import failure"
    _logger.warning(
        "HYDRA import failed unexpectedly: %s — module will be inert.",
        _exc,
        exc_info=True,
    )


def __getattr__(name: str):
    if name in _HYDRA_EXPORTS and not HAS_TORCH:
        if _IMPORT_ERROR is not None:
            raise ImportError(
                f"HYDRA export {name!r} is unavailable because {_UNAVAILABLE_REASON}. "
                "Install ML dependencies with: pip install -e '.[ml]'"
            ) from _IMPORT_ERROR
        raise ImportError(
            f"HYDRA export {name!r} is unavailable because PyTorch is not installed. "
            "Install ML dependencies with: pip install -e '.[ml]'"
        )
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
