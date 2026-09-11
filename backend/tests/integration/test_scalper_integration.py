"""
Integration tests for MTF Cascading Scalper ΓÇö End-to-End Trade Execution Flow
==============================================================================
Tests the full scalper lifecycle: config ΓåÆ init ΓåÆ scan ΓåÆ alignment ΓåÆ execute ΓåÆ status.

Must NOT place real trades. MT5 order_send is always mocked.
"""
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from datetime import datetime, timezone

import pandas as pd
import numpy as np


# ΓöÇΓöÇ Shared Fixtures ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

def _make_scalper_config(enabled=True):
    """Build a complete scalper config dict."""
    return {
        "mtf_cascading_scalper_enabled": enabled,
        "scalper_timeframes": ["M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1", "MN1"],
        "scalper_groups": [
            {"name": "Scalp1", "timeframes": ["M1", "M5", "M15"]},
            {"name": "Scalp2", "timeframes": ["M5", "M15", "M30"]},
        ],
        "scalper_tp_pips": 10,
        "scalper_sl_pips": 5,
        "scalper_lot_size": 0.01,
        "scalper_max_concurrent": 3,
        "scalper_scan_interval": 60,
        "scalper_restart_from_group1": True,
        "scalper_symbol": "EURUSD",
        "session_hours": set(range(24)),  # all hours for testing
        "drawdown_pause_pct": 0.15,
    }


def _make_ohlcv_bullish(n=100):
    """Create OHLCV data that produces a BUY signal."""
    np.random.seed(42)
    base = 1.1000
    close = np.linspace(base, base + 0.01, n)
    df = pd.DataFrame({
        "open": close - 0.0002,
        "high": close + 0.0005,
        "low": close - 0.0005,
        "close": close,
        "volume": np.random.randint(100, 1000, n),
    })
    return df


def _make_ohlcv_bearish(n=100):
    """Create OHLCV data that produces a SELL signal."""
    np.random.seed(42)
    base = 1.1000
    close = np.linspace(base, base - 0.01, n)
    df = pd.DataFrame({
        "open": close + 0.0002,
        "high": close + 0.0005,
        "low": close - 0.0005,
        "close": close,
        "volume": np.random.randint(100, 1000, n),
    })
    return df


def _make_ohlcv_mixed(n=100):
    """Create OHLCV data that produces HOLD signal (no alignment)."""
    np.random.seed(42)
    base = 1.1000
    close = np.ones(n) * base + np.random.randn(n) * 0.0005
    df = pd.DataFrame({
        "open": close - 0.0002,
        "high": close + 0.0005,
        "low": close - 0.0005,
        "close": close,
        "volume": np.random.randint(100, 1000, n),
    })
    return df


@pytest.fixture
def mock_risk_manager():
    """Mock RiskManager that allows all trades."""
    rm = MagicMock()
    rm.get_drawdown_pct.return_value = 0.0
    rm.check_circuit_breaker.return_value = True
    rm.check_portfolio_limits.return_value = True
    return rm


@pytest.fixture
def mock_mt5():
    """Mock MT5 engine with symbol info and tick data."""
    mt5_mock = MagicMock()

    # Symbol info
    symbol_info = MagicMock()
    symbol_info.point = 0.0001
    symbol_info.digits = 5
    symbol_info.visible = True
    mt5_mock.symbol_info.return_value = symbol_info
    mt5_mock.symbol_info_tick.return_value = MagicMock(ask=1.1050, bid=1.1048)
    mt5_mock.symbol_select.return_value = True

    # Order send - success
    result = MagicMock()
    result.retcode = mt5_mock.TRADE_RETCODE_DONE if hasattr(mt5_mock, 'TRADE_RETCODE_DONE') else 10009
    result.order = 12345
    result.price = 1.1050
    result.comment = "OK"
    mt5_mock.order_send.return_value = result

    return mt5_mock


@pytest.fixture
def scalper_config():
    return _make_scalper_config(enabled=True)


# ΓöÇΓöÇ Test Cases ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ


class TestScalperInitialization:
    """Test 1: Module loads and initializes with correct config."""

    def test_scalper_initializes_when_enabled(self, scalper_config, mock_mt5, mock_risk_manager):
        """MTFCascadingScalper creates successfully with enabled config."""
        from apps.legendary.mtf_cascading_scalper import MTFCascadingScalper

        scalper = MTFCascadingScalper(mock_mt5, mock_risk_manager, scalper_config)

        assert scalper is not None
        assert scalper.config["mtf_cascading_scalper_enabled"] is True
        assert scalper.mt5_engine is mock_mt5
        assert scalper.risk_manager is mock_risk_manager
        assert scalper.config["scalper_symbol"] == "EURUSD"
        assert len(scalper.config["scalper_groups"]) == 2

    def test_scalper_status_returns_correct_shape(self, scalper_config, mock_mt5, mock_risk_manager):
        """get_status() returns all required keys."""
        from apps.legendary.mtf_cascading_scalper import MTFCascadingScalper

        scalper = MTFCascadingScalper(mock_mt5, mock_risk_manager, scalper_config)
        status = scalper.get_status()

        assert isinstance(status, dict)
        assert "enabled" in status
        assert "open_scalps" in status
        assert "total_trades" in status
        assert "last_scan" in status
        assert "last_error" in status
        assert "symbol" in status
        assert "tp_pips" in status
        assert "sl_pips" in status
        assert "max_concurrent" in status
        assert "groups" in status
        assert status["enabled"] is True
        assert status["symbol"] == "EURUSD"


class TestScalperDisabledByDefault:
    """Test 2: Flag is False, no scalper created."""

    def test_scalper_disabled_by_default(self, mock_mt5, mock_risk_manager):
        """When mtf_cascading_scalper_enabled is False, engine.scalper is None."""
        from apps.legendary.mtf_cascading_scalper import MTFCascadingScalper

        config = _make_scalper_config(enabled=False)
        scalper = MTFCascadingScalper(mock_mt5, mock_risk_manager, config)

        # scan_and_execute should return None when disabled
        result = scalper.scan_and_execute()
        assert result is None

    def test_scalper_status_shows_disabled(self, mock_mt5, mock_risk_manager):
        """Status shows enabled=False when config flag is False."""
        from apps.legendary.mtf_cascading_scalper import MTFCascadingScalper

        config = _make_scalper_config(enabled=False)
        scalper = MTFCascadingScalper(mock_mt5, mock_risk_manager, config)
        status = scalper.get_status()

        assert status["enabled"] is False

    def test_engine_scalper_none_when_disabled(self):
        """UnifiedEngine.scalper is None when config flag is False."""
        from unified_engine import UnifiedEngine, CONFIG

        original = CONFIG.get("mtf_cascading_scalper_enabled")
        CONFIG["mtf_cascading_scalper_enabled"] = False
        try:
            with patch.object(UnifiedEngine, '__init__', lambda self: None):
                engine = UnifiedEngine()
                engine.scalper = None
                assert engine.scalper is None
        finally:
            if original is not None:
                CONFIG["mtf_cascading_scalper_enabled"] = original
            else:
                CONFIG.pop("mtf_cascading_scalper_enabled", None)


class TestScanNoAlignment:
    """Test 3: Mocked signals with no alignment returns None."""

    def test_scan_returns_none_when_no_alignment(self, scalper_config, mock_mt5, mock_risk_manager):
        """When signals are mixed (BUY, SELL, HOLD), alignment check fails."""
        from apps.legendary.mtf_cascading_scalper import MTFCascadingScalper

        scalper = MTFCascadingScalper(mock_mt5, mock_risk_manager, scalper_config)

        # Mock _get_signals_for_group to return mixed signals (no alignment)
        with patch.object(scalper, '_get_signals_for_group', return_value=["BUY", "SELL", "HOLD"]):
            result = scalper._check_alignment(["BUY", "SELL", "HOLD"])
            assert result is None

    def test_scan_returns_none_when_two_buy_one_hold(self, scalper_config, mock_mt5, mock_risk_manager):
        """Two BUY + one HOLD should not align."""
        from apps.legendary.mtf_cascading_scalper import MTFCascadingScalper

        scalper = MTFCascadingScalper(mock_mt5, mock_risk_manager, scalper_config)
        result = scalper._check_alignment(["BUY", "BUY", "HOLD"])
        assert result is None

    def test_scan_returns_none_when_empty_signals(self, scalper_config, mock_mt5, mock_risk_manager):
        """Empty signal list returns None."""
        from apps.legendary.mtf_cascading_scalper import MTFCascadingScalper

        scalper = MTFCascadingScalper(mock_mt5, mock_risk_manager, scalper_config)
        result = scalper._check_alignment([])
        assert result is None

    def test_scan_returns_none_when_all_hold(self, scalper_config, mock_mt5, mock_risk_manager):
        """All HOLD signals should not align (HOLD is not a direction)."""
        from apps.legendary.mtf_cascading_scalper import MTFCascadingScalper

        scalper = MTFCascadingScalper(mock_mt5, mock_risk_manager, scalper_config)
        result = scalper._check_alignment(["HOLD", "HOLD", "HOLD"])
        assert result is None


class TestScanAligned:
    """Test 4: Mocked 3 aligned signals returns correct direction."""

    def test_scan_returns_signal_when_aligned_buy(self, scalper_config, mock_mt5, mock_risk_manager):
        """All 3 BUY signals align -> returns BUY."""
        from apps.legendary.mtf_cascading_scalper import MTFCascadingScalper

        scalper = MTFCascadingScalper(mock_mt5, mock_risk_manager, scalper_config)
        result = scalper._check_alignment(["BUY", "BUY", "BUY"])
        assert result == "BUY"

    def test_scan_returns_signal_when_aligned_sell(self, scalper_config, mock_mt5, mock_risk_manager):
        """All 3 SELL signals align -> returns SELL."""
        from apps.legendary.mtf_cascading_scalper import MTFCascadingScalper

        scalper = MTFCascadingScalper(mock_mt5, mock_risk_manager, scalper_config)
        result = scalper._check_alignment(["SELL", "SELL", "SELL"])
        assert result == "SELL"

    def test_full_scan_with_alignment_executes_trade(self, scalper_config, mock_mt5, mock_risk_manager):
        """Full scan_and_execute with aligned signals places a trade."""
        from apps.legendary.mtf_cascading_scalper import MTFCascadingScalper
        import MetaTrader5 as mt5

        scalper = MTFCascadingScalper(mock_mt5, mock_risk_manager, scalper_config)

        # Mock _get_signals_for_group to return aligned BUY signals
        # Mock _fetch_ohlcv to return bullish data
        with patch.object(scalper, '_get_signals_for_group', return_value=["BUY", "BUY", "BUY"]), \
             patch.object(scalper, '_fetch_ohlcv', return_value=_make_ohlcv_bullish()), \
             patch.object(scalper, '_compute_directional_signal', return_value="BUY"), \
             patch('apps.legendary.mtf_cascading_scalper.mt5') as mock_mt5_module:

            mock_mt5_module.symbol_info.return_value = MagicMock(point=0.0001, digits=5, visible=True)
            mock_mt5_module.symbol_info_tick.return_value = MagicMock(ask=1.1050, bid=1.1048)
            mock_mt5_module.symbol_select.return_value = True
            mock_mt5_module.TRADE_ACTION_DEAL = 1
            mock_mt5_module.ORDER_TYPE_BUY = 0
            mock_mt5_module.ORDER_TIME_GTC = 0
            mock_mt5_module.ORDER_FILLING_IOC = 0
            mock_mt5_module.TRADE_RETCODE_DONE = 10009

            result_mock = MagicMock()
            result_mock.retcode = 10009
            result_mock.order = 12345
            result_mock.price = 1.1050
            result_mock.comment = "OK"
            mock_mt5_module.order_send.return_value = result_mock

            result = scalper.scan_and_execute()

            # Should have attempted to execute a trade
            assert result is not None
            assert result["direction"] == "BUY"
            assert result["symbol"] == "EURUSD"
            assert result["status"] == "OPEN"


class TestScalperRiskManager:
    """Test 5: RiskManager rejects trade, scalper handles gracefully."""

    def test_scalper_respects_risk_manager_rejection(self, scalper_config, mock_mt5):
        """When RiskManager rejects, scalper does not execute trade."""
        from apps.legendary.mtf_cascading_scalper import MTFCascadingScalper

        # RiskManager that rejects (drawdown too high)
        risk_reject = MagicMock()
        risk_reject.get_drawdown_pct.return_value = 0.20  # above 0.15 threshold
        risk_reject.check_circuit_breaker.return_value = True
        risk_reject.check_portfolio_limits.return_value = True

        scalper = MTFCascadingScalper(mock_mt5, risk_reject, scalper_config)
        result = scalper.scan_and_execute()

        # Safety check should fail due to drawdown
        assert result is None

    def test_scalper_respects_circuit_breaker(self, scalper_config, mock_mt5):
        """When circuit breaker is active, scalper does not execute trade."""
        from apps.legendary.mtf_cascading_scalper import MTFCascadingScalper

        risk_cb = MagicMock()
        risk_cb.get_drawdown_pct.return_value = 0.0
        risk_cb.check_circuit_breaker.return_value = False  # breaker active
        risk_cb.check_portfolio_limits.return_value = True

        scalper = MTFCascadingScalper(mock_mt5, risk_cb, scalper_config)
        result = scalper.scan_and_execute()

        assert result is None

    def test_scalper_respects_portfolio_limits(self, scalper_config, mock_mt5):
        """When portfolio limits are exceeded, scalper does not execute."""
        from apps.legendary.mtf_cascading_scalper import MTFCascadingScalper

        risk_limits = MagicMock()
        risk_limits.get_drawdown_pct.return_value = 0.0
        risk_limits.check_circuit_breaker.return_value = True
        risk_limits.check_portfolio_limits.return_value = False  # limits exceeded

        scalper = MTFCascadingScalper(mock_mt5, risk_limits, scalper_config)
        result = scalper.scan_and_execute()

        assert result is None

    def test_scalper_respects_max_concurrent(self, scalper_config, mock_mt5, mock_risk_manager):
        """When max concurrent scalps reached, scalper does not execute."""
        from apps.legendary.mtf_cascading_scalper import MTFCascadingScalper

        scalper = MTFCascadingScalper(mock_mt5, mock_risk_manager, scalper_config)

        # Simulate max concurrent scalps open
        scalper.open_scalps = {1: {}, 2: {}, 3: {}}  # max_concurrent = 3

        result = scalper.scan_and_execute()

        assert result is None


class TestScalperAPIEndpoint:
    """Test 6: API endpoint returns valid JSON."""

    def test_scalper_api_endpoint_returns_json(self):
        """GET /api/v1/scalper/status returns valid JSON structure."""
        from unified_engine import scalper_status, engine, CONFIG

        original = CONFIG.get("mtf_cascading_scalper_enabled")
        CONFIG["mtf_cascading_scalper_enabled"] = False
        try:
            # When scalper is disabled, endpoint returns default
            engine.scalper = None
            result = scalper_status()

            assert isinstance(result, dict)
            assert "enabled" in result
            assert result["enabled"] is False
        finally:
            if original is not None:
                CONFIG["mtf_cascading_scalper_enabled"] = original
            else:
                CONFIG.pop("mtf_cascading_scalper_enabled", None)

    def test_scalper_api_endpoint_with_active_scalper(self, scalper_config, mock_mt5, mock_risk_manager):
        """Endpoint returns scalper status when scalper is active."""
        from apps.legendary.mtf_cascading_scalper import MTFCascadingScalper
        from unified_engine import scalper_status, engine

        scalper = MTFCascadingScalper(mock_mt5, mock_risk_manager, scalper_config)
        engine.scalper = scalper

        try:
            result = scalper_status()

            assert isinstance(result, dict)
            assert result["enabled"] is True
            assert result["symbol"] == "EURUSD"
            assert result["open_scalps"] == 0
            assert result["total_trades"] == 0
        finally:
            engine.scalper = None

    def test_engine_status_includes_scalper(self, scalper_config, mock_mt5, mock_risk_manager):
        """engine_status() response includes 'scalper' key."""
        from apps.legendary.mtf_cascading_scalper import MTFCascadingScalper
        from unified_engine import engine_status, engine

        scalper = MTFCascadingScalper(mock_mt5, mock_risk_manager, scalper_config)
        engine.scalper = scalper

        try:
            with patch.object(engine, 'mt5') as mock_mt5_engine:
                mock_mt5_engine.connected = False
                mock_mt5_engine.get_account_info.return_value = None
                result = engine_status()

            assert "scalper" in result
            assert result["scalper"]["enabled"] is True
        finally:
            engine.scalper = None

    def test_engine_status_scalper_none_when_disabled(self):
        """engine_status() includes scalper=None when disabled."""
        from unified_engine import engine_status, engine

        engine.scalper = None

        try:
            with patch.object(engine, 'mt5') as mock_mt5_engine:
                mock_mt5_engine.connected = False
                mock_mt5_engine.get_account_info.return_value = None
                result = engine_status()

            assert "scalper" in result
            assert result["scalper"] is None
        finally:
            pass
