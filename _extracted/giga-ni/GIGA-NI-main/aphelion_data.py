"""Deprecated legacy entrypoint for the removed monolithic data pipeline."""

from __future__ import annotations

import warnings

warnings.warn(
    "aphelion_data.py is deprecated and no longer maintained. "
    "Use mt5pipe and aphelion.gold_feature_pack instead. "
    "See docs/aphelion_data_migration.md for the migration guide.",
    DeprecationWarning,
    stacklevel=2,
)

raise ImportError(
    "aphelion_data has been removed. Import from mt5pipe or aphelion.gold_feature_pack instead. "
    "See _archive/deprecated/aphelion_data.py.bak for the legacy implementation."
)
