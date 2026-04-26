"""Architectural boundary tests for the APHELION pipeline.

These tests verify that:
1. The canonical StateSnapshot contract works end-to-end
2. The shared execution primitives (build_order_from_signal, apply_enforcement,
   build_trade_proposal, compute_commission) are consistent
3. Evolution modules do NOT import or create Order objects directly
4. The pipeline data contract is respected
"""

from __future__ import annotations

import ast
import importlib
import inspect
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest


# ── Paths ────────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent
APHELION_ROOT = REPO_ROOT / "aphelion"


# ═══════════════════════════════════════════════════════════════════════════════
# 1. StateSnapshot contract tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestStateSnapshot:
    """Verify the canonical pipeline data contract."""

    def test_import(self):
        from aphelion.core.state import StateSnapshot, build_state_snapshot
        assert StateSnapshot is not None
        assert build_state_snapshot is not None

    def test_construction_minimal(self):
        from aphelion.core.state import StateSnapshot
        ss = StateSnapshot(
            timestamp_utc=datetime.now(timezone.utc),
            symbol="XAUUSD",
            timeframe="1m",
            current_price=1944.50,
            atr=2.5,
        )
        assert ss.symbol == "XAUUSD"
        assert ss.current_price == 1944.50
        assert ss.features == {}
        assert ss.warmup_complete is False

    def test_construction_with_feature_snapshot(self):
        from aphelion.core.state import build_state_snapshot
        from aphelion.feature_engine.snapshot import build_feature_snapshot
        import time

        fs = build_feature_snapshot(
            ts_event_ns=int(time.time() * 1e9),
            symbol="XAUUSD",
            timeframe="1m",
            feature_version="8.1.0",
            warmup_complete=True,
            missing_count=0,
            features={"vwap": {"session_vwap": 1944.5}},
            metadata={"close": 1944.5, "atr": 2.5},
        )

        ss = build_state_snapshot(
            symbol="XAUUSD",
            timeframe="1m",
            current_price=1944.50,
            atr=2.5,
            feature_snapshot=fs,
            equity=10_000.0,
        )
        assert ss.warmup_complete is True
        assert ss.feature_snapshot is fs
        assert "vwap.session_vwap" in ss.features

    def test_immutable(self):
        from aphelion.core.state import StateSnapshot
        ss = StateSnapshot(
            timestamp_utc=datetime.now(timezone.utc),
            symbol="XAUUSD",
            timeframe="1m",
            current_price=1944.50,
            atr=2.5,
        )
        with pytest.raises(AttributeError):
            ss.current_price = 2000.0  # type: ignore[misc]

    def test_exported_from_core(self):
        from aphelion.core import StateSnapshot, build_state_snapshot
        assert StateSnapshot is not None
        assert build_state_snapshot is not None


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Shared execution primitives tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestSharedExecutionPrimitives:
    """Verify the canonical execution helpers."""

    def test_build_order_from_signal_buy(self):
        from aphelion.core.execution import build_order_from_signal
        order = build_order_from_signal(
            direction=1,
            current_price=1944.50,
            atr=2.5,
            equity=10_000.0,
            size_pct=0.015,
            proposed_by="TEST",
        )
        assert order is not None
        assert order.side.value == "BUY"
        assert order.stop_loss < 1944.50
        assert order.take_profit > 1944.50
        assert order.size_lots >= 0.01

    def test_build_order_from_signal_sell(self):
        from aphelion.core.execution import build_order_from_signal
        order = build_order_from_signal(
            direction=-1,
            current_price=1944.50,
            atr=2.5,
            equity=10_000.0,
            size_pct=0.015,
            proposed_by="TEST",
        )
        assert order is not None
        assert order.side.value == "SELL"
        assert order.stop_loss > 1944.50
        assert order.take_profit < 1944.50

    def test_build_order_from_signal_flat_returns_none(self):
        from aphelion.core.execution import build_order_from_signal
        order = build_order_from_signal(
            direction=0,
            current_price=1944.50,
            atr=2.5,
            equity=10_000.0,
            size_pct=0.015,
        )
        assert order is None

    def test_build_order_from_signal_zero_size_returns_none(self):
        from aphelion.core.execution import build_order_from_signal
        order = build_order_from_signal(
            direction=1,
            current_price=1944.50,
            atr=2.5,
            equity=10_000.0,
            size_pct=0.0,
        )
        assert order is None

    def test_build_order_clamps_to_sentinel_max(self):
        from aphelion.core.config import SENTINEL
        from aphelion.core.execution import build_order_from_signal
        order = build_order_from_signal(
            direction=1,
            current_price=1944.50,
            atr=2.5,
            equity=10_000.0,
            size_pct=0.99,  # way above SENTINEL max
        )
        assert order is not None
        assert order.size_pct <= SENTINEL.max_position_pct

    def test_compute_commission(self):
        from aphelion.core.execution import compute_commission
        assert compute_commission(1.0, 7.0) == 7.0
        assert compute_commission(0.5, 7.0) == 3.5
        assert compute_commission(0.0, 7.0) == 0.0

    def test_build_trade_proposal_from_order(self):
        from aphelion.backtest.order import Order, OrderSide, OrderType
        from aphelion.core.execution import build_trade_proposal
        order = Order(
            order_id="TEST-001",
            symbol="XAUUSD",
            order_type=OrderType.MARKET,
            side=OrderSide.BUY,
            size_lots=0.10,
            entry_price=0.0,
            stop_loss=1940.0,
            take_profit=1950.0,
            size_pct=0.015,
            proposed_by="TEST",
        )
        proposal = build_trade_proposal(order, 1944.50)
        assert proposal.symbol == "XAUUSD"
        assert proposal.direction == "LONG"
        assert proposal.entry_price == 1944.50
        assert proposal.stop_loss == 1940.0
        assert proposal.take_profit == 1950.0


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Evolution containment tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestEvolutionContainment:
    """Verify that evolution modules do NOT contain execution logic."""

    def _get_imports_from_file(self, filepath: Path) -> set[str]:
        """Parse a Python file and return all imported module names."""
        source = filepath.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=str(filepath))
        except SyntaxError:
            return set()

        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.add(node.module)
        return imports

    def test_prometheus_evaluator_uses_canonical_order_factory(self):
        """GenomeStrategy must use build_order_from_signal, not construct Order directly."""
        filepath = APHELION_ROOT / "evolution" / "prometheus" / "evaluator.py"
        source = filepath.read_text(encoding="utf-8")
        # Should import from core.execution
        assert "from aphelion.core.execution import" in source
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "__call__":
                # Must NOT directly instantiate Order()
                for child in ast.walk(node):
                    if isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
                        assert child.func.id != "Order", \
                            "GenomeStrategy.__call__ must not construct Order directly"
                # Must call build_order_from_signal
                calls_factory = False
                for child in ast.walk(node):
                    if isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
                        if child.func.id == "build_order_from_signal":
                            calls_factory = True
                assert calls_factory, \
                    "GenomeStrategy.__call__ must invoke build_order_from_signal"

    def test_evolution_modules_no_direct_order_creation(self):
        """No evolution module should directly construct Order objects
        (except through the canonical factory)."""
        evolution_dir = APHELION_ROOT / "evolution"
        violations = []

        for py_file in evolution_dir.rglob("*.py"):
            if py_file.name == "__init__.py":
                continue
            source = py_file.read_text(encoding="utf-8")
            try:
                tree = ast.parse(source)
            except SyntaxError:
                continue

            for node in ast.walk(tree):
                # Check for Order(...) constructor calls
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    if node.func.id == "Order":
                        rel = py_file.relative_to(APHELION_ROOT)
                        violations.append(f"{rel}:{node.lineno}")

        assert not violations, (
            f"Evolution modules must not construct Order directly: {violations}"
        )

    def test_evolution_modules_no_private_portfolio_access(self):
        """No evolution module should directly access portfolio._open_positions as an attribute."""
        evolution_dir = APHELION_ROOT / "evolution"
        for py_file in evolution_dir.rglob("*.py"):
            source = py_file.read_text(encoding="utf-8")
            # Check for actual attribute access pattern (portfolio._open_positions)
            # not gene/parameter names like "max_open_positions"
            assert "portfolio._open_positions" not in source, (
                f"{py_file.relative_to(APHELION_ROOT)} accesses private portfolio._open_positions"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Pipeline consistency tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestPipelineConsistency:
    """Verify that backtest and paper execution share the same enforcement logic."""

    def test_enforcement_uses_shared_helper_backtest(self):
        """BacktestEngine._apply_execution_enforcement delegates to shared helper."""
        source = (APHELION_ROOT / "backtest" / "engine.py").read_text(encoding="utf-8")
        assert "apply_enforcement" in source, \
            "BacktestEngine must use shared apply_enforcement"

    def test_enforcement_uses_shared_helper_paper(self):
        """PaperExecutor.submit_order delegates to shared helper."""
        source = (APHELION_ROOT / "risk" / "sentinel" / "execution" / "paper.py").read_text(encoding="utf-8")
        assert "apply_enforcement" in source, \
            "PaperExecutor must use shared apply_enforcement"

    def test_broker_sim_uses_shared_trade_proposal(self):
        """BrokerSimulator._validate_trade_proposal uses shared factory."""
        source = (APHELION_ROOT / "backtest" / "broker_sim.py").read_text(encoding="utf-8")
        assert "build_trade_proposal" in source, \
            "BrokerSimulator must use shared build_trade_proposal"

    def test_execution_bridge_uses_canonical_order_factory(self):
        """SignalOrderAdapter uses build_order_from_signal."""
        source = (APHELION_ROOT / "integrations" / "supersystem" / "execution_bridge.py").read_text(encoding="utf-8")
        assert "build_order_from_signal" in source, \
            "SignalOrderAdapter must use shared build_order_from_signal"

    def test_portfolio_has_public_position_count(self):
        """Portfolio exposes get_open_position_count() as a public method."""
        from aphelion.backtest.portfolio import Portfolio
        p = Portfolio(10_000.0)
        assert hasattr(p, "get_open_position_count")
        assert p.get_open_position_count() == 0
