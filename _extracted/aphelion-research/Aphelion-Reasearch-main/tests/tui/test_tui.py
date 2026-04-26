"""
Tests for APHELION TUI v2 (Bloomberg-grade).
Covers state model, screen builders, widgets, dashboard compositor,
and the unified AphelionTUI entry-point.
"""

from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime, timezone

import pytest

from aphelion.tui.state import (
    TUIState,
    HydraSignalView,
    SentinelView,
    EquityView,
    PositionView,
    PriceView,
    AlertEntry,
    LogEntry,
)
from aphelion.tui.app import AphelionTUI, TUIConfig

# Rich is required for TUI
rich = pytest.importorskip("rich")

from aphelion.tui.screens.header import build_header
from aphelion.tui.screens.hydra_panel import build_hydra_panel
from aphelion.tui.screens.sentinel_panel import build_sentinel_panel
from aphelion.tui.screens.positions import build_positions_panel
from aphelion.tui.screens.equity import build_equity_panel
from aphelion.tui.screens.event_log import build_log_panel
from aphelion.tui.screens.dashboard import build_dashboard_layout
from aphelion.tui.screens.performance import build_performance_panel

from rich.panel import Panel
from rich.layout import Layout


# ===========================================================================
# State dataclass tests
# ===========================================================================

class TestTUIState:
    """TUIState dataclass behaviour."""

    def test_default_creation(self):
        state = TUIState()
        assert state.session_name == "Paper-01"
        assert state.bars_processed == 0
        assert state.market_open is False
        assert isinstance(state.hydra, HydraSignalView)
        assert isinstance(state.sentinel, SentinelView)
        assert isinstance(state.equity, EquityView)
        assert isinstance(state.price, PriceView)
        assert state.positions == []
        assert state.log == []
        assert state.alerts == []

    def test_push_log(self):
        state = TUIState(max_log_lines=5)
        for i in range(10):
            state.push_log("INFO", f"msg-{i}")
        assert len(state.log) == 5
        assert state.log[0].message == "msg-5"
        assert state.log[-1].message == "msg-9"

    def test_push_log_levels(self):
        state = TUIState()
        state.push_log("FILL", "Order filled LONG 0.10 lots")
        state.push_log("REJECT", "SENTINEL blocked: max exposure")
        state.push_log("ERROR", "Connection lost")
        assert state.log[0].level == "FILL"
        assert state.log[1].level == "REJECT"
        assert state.log[2].level == "ERROR"

    def test_push_alert(self):
        state = TUIState(max_alerts=3)
        for i in range(5):
            state.push_alert("WARNING", f"Alert-{i}", f"msg-{i}")
        assert len(state.alerts) == 3
        assert state.alerts[0].title == "Alert-2"

    def test_unacknowledged_alerts(self):
        state = TUIState()
        state.push_alert("WARNING", "A1", "msg")
        state.push_alert("CRITICAL", "A2", "msg")
        state.alerts[0].acknowledged = True
        assert len(state.unacknowledged_alerts) == 1
        assert state.unacknowledged_alerts[0].title == "A2"

    def test_push_equity_tick(self):
        state = TUIState()
        state.push_equity_tick(100_000.0)
        state.push_equity_tick(101_000.0)
        state.push_equity_tick(99_000.0)
        assert len(state.equity.equity_history) == 3
        assert state.equity.max_drawdown_pct > 0

    def test_push_price_tick(self):
        state = TUIState()
        state.push_price_tick(2350.0, 2350.5)
        assert state.price.bid == 2350.0
        assert state.price.ask == 2350.5
        assert state.price.spread == pytest.approx(0.5)
        assert len(state.price.tick_history) == 1

    def test_win_rate_property(self):
        state = TUIState()
        assert state.win_rate == 0.0
        state.equity.total_trades = 10
        state.equity.winning_trades = 7
        assert state.win_rate == pytest.approx(0.7)

    def test_hydra_signal_defaults(self):
        h = HydraSignalView()
        assert h.direction == "FLAT"
        assert h.confidence == 0.0
        assert len(h.probs_5m) == 3
        assert len(h.gate_weights) == 4
        assert len(h.moe_routing) == 4
        assert h.signal_count == 0
        assert isinstance(h.confidence_history, deque)

    def test_sentinel_view_defaults(self):
        s = SentinelView()
        assert s.trading_allowed is True
        assert s.l3_triggered is False
        assert s.max_positions == 3
        assert isinstance(s.drawdown_history, deque)
        assert s.breaker_since is None

    def test_equity_view_defaults(self):
        e = EquityView()
        assert e.account_equity == 100_000.0
        assert e.total_trades == 0
        assert e.sharpe_ratio == 0.0
        assert e.profit_factor == 0.0
        assert isinstance(e.equity_history, deque)

    def test_position_view_fields(self):
        p = PositionView(
            position_id="P001",
            direction="LONG",
            entry_price=2350.0,
            current_price=2355.0,
            stop_loss=2340.0,
            take_profit=2370.0,
            size_lots=0.10,
            unrealized_pnl=50.0,
            risk_reward=2.0,
            hold_bars=15,
        )
        assert p.direction == "LONG"
        assert p.unrealized_pnl == 50.0
        assert p.risk_reward == 2.0
        assert p.hold_bars == 15

    def test_price_view_defaults(self):
        p = PriceView()
        assert p.symbol == "XAUUSD"
        assert p.bid == 0.0
        assert isinstance(p.tick_history, deque)

    def test_alert_entry_defaults(self):
        a = AlertEntry(severity="CRITICAL", title="Test", message="msg")
        assert a.acknowledged is False
        assert a.timestamp is not None

    def test_max_drawdown_tracking(self):
        state = TUIState()
        state.equity.session_peak = 100_000.0
        state.push_equity_tick(100_000.0)
        state.push_equity_tick(97_000.0)
        assert state.equity.max_drawdown_pct == pytest.approx(0.03)

    def test_system_stats_default(self):
        state = TUIState()
        assert state.cpu_usage == 0.0
        assert state.memory_mb == 0.0
        assert state.latency_ms == 0.0


# ===========================================================================
# Widget tests
# ===========================================================================

class TestWidgets:
    """Test custom rendering widgets."""

    def test_sparkline_empty(self):
        from aphelion.tui.widgets.sparkline import render_sparkline
        txt = render_sparkline([], width=20)
        assert len(str(txt)) == 20

    def test_sparkline_data(self):
        from aphelion.tui.widgets.sparkline import render_sparkline
        data = [100, 102, 101, 105, 103, 108]
        txt = render_sparkline(data, width=30)
        assert len(str(txt)) > 0

    def test_confidence_sparkline(self):
        from aphelion.tui.widgets.sparkline import render_confidence_sparkline
        data = [0.3, 0.5, 0.7, 0.8, 0.6]
        txt = render_confidence_sparkline(data, width=20)
        assert len(str(txt)) > 0

    def test_gauge_basic(self):
        from aphelion.tui.widgets.gauge import render_gauge
        txt = render_gauge(3.0, 10.0, width=20)
        assert "3.0" in str(txt)

    def test_gauge_zero_max(self):
        from aphelion.tui.widgets.gauge import render_gauge
        txt = render_gauge(0.0, 0.0, width=10)
        assert "0.0" in str(txt)

    def test_breaker_indicator_clear(self):
        from aphelion.tui.widgets.gauge import render_breaker_indicator
        txt = render_breaker_indicator("L1", False)
        assert "CLEAR" in str(txt)

    def test_breaker_indicator_triggered(self):
        from aphelion.tui.widgets.gauge import render_breaker_indicator
        txt = render_breaker_indicator("L2", True)
        assert "TRIPPED" in str(txt)

    def test_mini_bar(self):
        from aphelion.tui.widgets.gauge import render_mini_bar
        txt = render_mini_bar(5.0, 10.0, width=10)
        assert len(str(txt)) > 0

    def test_feature_heatmap_empty(self):
        from aphelion.tui.widgets.heatmap import render_feature_heatmap
        table = render_feature_heatmap([])
        assert table is not None

    def test_feature_heatmap_data(self):
        from aphelion.tui.widgets.heatmap import render_feature_heatmap
        feats = [("rsi", 0.15), ("atr", 0.12), ("vpin", 0.08)]
        table = render_feature_heatmap(feats, max_features=5)
        assert table is not None

    def test_gate_weights(self):
        from aphelion.tui.widgets.heatmap import render_gate_weights
        table = render_gate_weights([0.4, 0.3, 0.2, 0.1], ["A", "B", "C", "D"])
        assert table is not None

    def test_price_ticker_zero(self):
        from aphelion.tui.widgets.ticker import render_price_ticker
        p = PriceView()
        txt = render_price_ticker(p)
        assert "XAUUSD" in str(txt)

    def test_price_ticker_data(self):
        from aphelion.tui.widgets.ticker import render_price_ticker
        p = PriceView(
            bid=2350.0, ask=2350.5, last=2350.25,
            change=12.3, change_pct=0.52, spread=0.5,
            high=2365.0, low=2340.0,
        )
        txt = render_price_ticker(p)
        s = str(txt)
        assert "2,350" in s or "2350" in s
        assert "12.3" in s or "12.30" in s

    def test_mini_chart_empty(self):
        from aphelion.tui.widgets.mini_chart import render_mini_chart
        result = render_mini_chart([], width=30)
        assert "No data" in result

    def test_mini_chart_data(self):
        from aphelion.tui.widgets.mini_chart import render_mini_chart
        data = [100.0 + i * 0.5 for i in range(30)]
        result = render_mini_chart(data, width=30, height=5)
        assert len(result.split("\n")) >= 5

    def test_ohlc_bars(self):
        from aphelion.tui.widgets.mini_chart import render_ohlc_bars
        o = [100.0, 101.0, 102.0]
        h = [103.0, 104.0, 105.0]
        l = [99.0, 100.0, 101.0]
        c = [102.0, 103.0, 104.0]
        result = render_ohlc_bars(o, h, l, c, width=10, height=5)
        assert len(result) > 0


# ===========================================================================
# Screen builder tests
# ===========================================================================

class TestScreenBuilders:
    """Each screen builder produces a valid Rich Panel / Layout."""

    @pytest.fixture
    def state(self):
        return TUIState(
            session_name="Test-Session",
            market_open=True,
            current_session="LONDON",
            current_time=datetime(2025, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            bars_processed=42,
        )

    def test_header_returns_panel(self, state):
        panel = build_header(state)
        assert isinstance(panel, Panel)

    def test_header_with_alerts(self, state):
        state.push_alert("CRITICAL", "Test", "msg")
        panel = build_header(state)
        assert isinstance(panel, Panel)

    def test_header_with_system_stats(self, state):
        state.cpu_usage = 45.0
        state.memory_mb = 512.0
        state.latency_ms = 10.0
        state.uptime_seconds = 3661
        panel = build_header(state)
        assert isinstance(panel, Panel)

    def test_hydra_panel_returns_panel(self, state):
        state.hydra.direction = "LONG"
        state.hydra.confidence = 0.78
        state.hydra.uncertainty = 0.12
        state.hydra.horizon_agreement = 1.0
        state.hydra.probs_1h = [0.1, 0.12, 0.78]
        state.hydra.gate_weights = [0.4, 0.3, 0.2, 0.1]
        state.hydra.moe_routing = [0.5, 0.2, 0.2, 0.1]
        state.hydra.top_features = [("vpin", 0.15), ("atr", 0.12)]
        panel = build_hydra_panel(state)
        assert isinstance(panel, Panel)

    def test_hydra_panel_flat(self, state):
        panel = build_hydra_panel(state)
        assert isinstance(panel, Panel)

    def test_hydra_panel_with_confidence_history(self, state):
        for v in [0.5, 0.6, 0.7, 0.8]:
            state.hydra.confidence_history.append(v)
        state.hydra.signal_count = 4
        panel = build_hydra_panel(state)
        assert isinstance(panel, Panel)

    def test_sentinel_panel_returns_panel(self, state):
        panel = build_sentinel_panel(state)
        assert isinstance(panel, Panel)

    def test_sentinel_panel_with_triggers(self, state):
        state.sentinel.l1_triggered = True
        state.sentinel.l3_triggered = True
        state.sentinel.trading_allowed = False
        state.sentinel.circuit_breaker_active = True
        state.sentinel.breaker_since = datetime.now(timezone.utc)
        panel = build_sentinel_panel(state)
        assert isinstance(panel, Panel)

    def test_sentinel_panel_with_dd_history(self, state):
        for v in [0.01, 0.02, 0.015, 0.03]:
            state.sentinel.drawdown_history.append(v)
        panel = build_sentinel_panel(state)
        assert isinstance(panel, Panel)

    def test_positions_panel_empty(self, state):
        panel = build_positions_panel(state)
        assert isinstance(panel, Panel)

    def test_positions_panel_with_data(self, state):
        state.positions = [
            PositionView(
                position_id="P001",
                direction="LONG",
                entry_price=2350.0,
                current_price=2358.0,
                stop_loss=2340.0,
                take_profit=2370.0,
                size_lots=0.10,
                unrealized_pnl=80.0,
                risk_reward=2.0,
                hold_bars=15,
            ),
            PositionView(
                position_id="P002",
                direction="SHORT",
                entry_price=2360.0,
                current_price=2362.0,
                stop_loss=2370.0,
                take_profit=2350.0,
                size_lots=0.05,
                unrealized_pnl=-10.0,
                risk_reward=1.0,
                hold_bars=5,
            ),
        ]
        panel = build_positions_panel(state)
        assert isinstance(panel, Panel)

    def test_equity_panel_returns_panel(self, state):
        state.equity.daily_pnl = 150.0
        state.equity.total_trades = 5
        state.equity.winning_trades = 3
        state.equity.losing_trades = 2
        panel = build_equity_panel(state)
        assert isinstance(panel, Panel)

    def test_equity_panel_negative(self, state):
        state.equity.daily_pnl = -200.0
        panel = build_equity_panel(state)
        assert isinstance(panel, Panel)

    def test_equity_panel_with_sparkline(self, state):
        for v in [100000, 100500, 101000, 100800, 101500]:
            state.equity.equity_history.append(v)
        state.equity.sharpe_ratio = 2.1
        state.equity.profit_factor = 1.8
        state.equity.max_drawdown_pct = 0.02
        panel = build_equity_panel(state)
        assert isinstance(panel, Panel)

    def test_equity_panel_with_streaks(self, state):
        state.equity.consecutive_wins = 5
        state.equity.best_trade = 250.0
        state.equity.worst_trade = -100.0
        panel = build_equity_panel(state)
        assert isinstance(panel, Panel)

    def test_log_panel_empty(self, state):
        panel = build_log_panel(state)
        assert isinstance(panel, Panel)

    def test_log_panel_with_entries(self, state):
        state.push_log("FILL", "Filled LONG 0.10 at 2350.50")
        state.push_log("INFO", "Bar 43 processed")
        state.push_log("SENTINEL", "Exposure check passed")
        state.push_log("HYDRA", "Signal: LONG 85%")
        state.push_log("ERROR", "Feed timeout")
        panel = build_log_panel(state)
        assert isinstance(panel, Panel)

    def test_log_panel_max_visible(self, state):
        for i in range(50):
            state.push_log("INFO", f"msg-{i}")
        panel = build_log_panel(state, max_visible=10)
        assert isinstance(panel, Panel)

    def test_performance_panel(self, state):
        state.equity.total_trades = 20
        state.equity.winning_trades = 13
        state.equity.losing_trades = 7
        state.equity.sharpe_ratio = 2.1
        state.equity.profit_factor = 1.8
        state.equity.max_drawdown_pct = 0.025
        state.equity.avg_win = 120.0
        state.equity.avg_loss = -80.0
        state.equity.best_trade = 350.0
        state.equity.worst_trade = -200.0
        panel = build_performance_panel(state)
        assert isinstance(panel, Panel)

    def test_performance_panel_empty(self, state):
        panel = build_performance_panel(state)
        assert isinstance(panel, Panel)

    def test_performance_panel_high_risk(self, state):
        state.equity.max_drawdown_pct = 0.08
        state.equity.profit_factor = 0.8
        panel = build_performance_panel(state)
        assert isinstance(panel, Panel)


# ===========================================================================
# Dashboard compositor + multi-view
# ===========================================================================

class TestDashboardLayout:
    """Full dashboard layout integration with multi-view support."""

    def test_build_layout_returns_layout(self):
        state = TUIState()
        layout = build_dashboard_layout(state)
        assert isinstance(layout, Layout)

    def test_overview_view(self):
        state = TUIState(market_open=True, bars_processed=100)
        layout = build_dashboard_layout(state, view="overview")
        assert isinstance(layout, Layout)

    def test_hydra_view(self):
        state = TUIState()
        state.hydra.direction = "LONG"
        state.hydra.confidence = 0.85
        layout = build_dashboard_layout(state, view="hydra")
        assert isinstance(layout, Layout)

    def test_risk_view(self):
        state = TUIState()
        state.sentinel.l1_triggered = True
        layout = build_dashboard_layout(state, view="risk")
        assert isinstance(layout, Layout)

    def test_analytics_view(self):
        state = TUIState()
        state.equity.total_trades = 50
        layout = build_dashboard_layout(state, view="analytics")
        assert isinstance(layout, Layout)

    def test_logs_view(self):
        state = TUIState()
        for i in range(30):
            state.push_log("INFO", f"log-{i}")
        layout = build_dashboard_layout(state, view="logs")
        assert isinstance(layout, Layout)

    def test_layout_with_full_state(self):
        state = TUIState(
            market_open=True,
            bars_processed=100,
        )
        state.hydra.direction = "SHORT"
        state.hydra.confidence = 0.65
        state.sentinel.l1_triggered = True
        state.equity.daily_pnl = -50.0
        state.positions.append(PositionView(
            position_id="P123",
            direction="SHORT",
            entry_price=2400.0,
            current_price=2395.0,
            size_lots=0.10,
            unrealized_pnl=50.0,
        ))
        state.push_log("FILL", "Opened SHORT 0.10")
        state.push_alert("WARNING", "Vol spike", "ATR > 3x normal")
        layout = build_dashboard_layout(state)
        assert isinstance(layout, Layout)

    def test_all_views_produce_layout(self):
        state = TUIState()
        for view in ["overview", "hydra", "risk", "analytics", "logs"]:
            layout = build_dashboard_layout(state, view=view)
            assert isinstance(layout, Layout), f"Failed for view={view}"


# ===========================================================================
# TUI Config
# ===========================================================================

class TestTUIConfig:
    """TUIConfig dataclass."""

    def test_defaults(self):
        cfg = TUIConfig()
        assert cfg.refresh_rate == 0.25
        assert cfg.max_log_lines == 200
        assert cfg.initial_view == "overview"
        assert cfg.theme == "bloomberg"

    def test_custom(self):
        cfg = TUIConfig(refresh_rate=0.1, initial_view="hydra", compact_mode=True)
        assert cfg.refresh_rate == 0.1
        assert cfg.initial_view == "hydra"
        assert cfg.compact_mode is True


# ===========================================================================
# AphelionTUI entry-point
# ===========================================================================

class TestAphelionTUI:
    """Test the unified TUI entry-point."""

    def test_creation_default(self):
        tui = AphelionTUI()
        assert tui.state is not None
        assert isinstance(tui.state, TUIState)

    def test_creation_with_state(self):
        state = TUIState(session_name="My-Session")
        tui = AphelionTUI(state=state)
        assert tui.state.session_name == "My-Session"

    def test_creation_with_config(self):
        cfg = TUIConfig(refresh_rate=0.1, initial_view="risk")
        tui = AphelionTUI(config=cfg)
        assert tui.state is not None

    def test_stop_method(self):
        tui = AphelionTUI()
        tui.stop()  # Should not raise
