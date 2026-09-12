"""Tests for Unified Risk Manager — Single Source of Truth."""

import pytest
from datetime import datetime, timezone


class TestUnifiedRiskManager:
    """Test the RiskManager in unified_engine.py is the single source of truth."""

    def test_risk_manager_class_exists(self):
        """RiskManager class should exist in unified_engine."""
        import importlib
        mod = importlib.import_module("unified_engine")
        assert hasattr(mod, "RiskManager")

    def test_risk_manager_instantiation(self):
        """RiskManager should instantiate with default values."""
        import importlib
        mod = importlib.import_module("unified_engine")
        rm = mod.RiskManager()
        assert rm.balance == 10000.0
        assert rm.peak_balance == 10000.0
        assert rm.consecutive_losses == 0
        assert rm.circuit_breaker_state == "CLOSED"

    def test_drawdown_calculation(self):
        """Drawdown should be (peak - current) / peak."""
        import importlib
        mod = importlib.import_module("unified_engine")
        rm = mod.RiskManager()
        rm.balance = 9500
        rm.peak_balance = 10000
        assert rm.get_drawdown_pct() == pytest.approx(0.05, abs=0.001)

    def test_risk_multiplier_normal(self):
        """Risk multiplier should be 1.0 when drawdown is low."""
        import importlib
        mod = importlib.import_module("unified_engine")
        rm = mod.RiskManager()
        rm.balance = 9900
        rm.peak_balance = 10000
        assert rm.get_risk_multiplier() == 1.0

    def test_circuit_breaker_opens_after_losses(self):
        """Circuit breaker should OPEN after configured consecutive losses."""
        import importlib
        mod = importlib.import_module("unified_engine")
        rm = mod.RiskManager()
        # Record 3 consecutive losses (default threshold)
        for _ in range(3):
            rm.record_trade_result(-10.0, -0.001)
        assert rm.circuit_breaker_state == "OPEN"

    def test_daily_tracking(self):
        """Daily P&L and trade count should be tracked."""
        import importlib
        mod = importlib.import_module("unified_engine")
        rm = mod.RiskManager()
        rm.record_trade_result(50.0, 0.005)
        rm.record_trade_result(-20.0, -0.002)
        assert rm.daily_trades == 2
        assert rm.daily_pnl_dollar == pytest.approx(30.0, abs=0.01)

    def test_position_sizing_returns_positive(self):
        """Position sizing should return positive lots for valid inputs."""
        import importlib
        mod = importlib.import_module("unified_engine")
        rm = mod.RiskManager()
        lots = rm.calculate_position_size(
            price=1.0850, atr=0.005, confidence=0.7,
            session_hour=14, volatility=0.01, symbol="EURUSD"
        )
        assert lots > 0
        assert lots <= 0.50  # Max lot limit

    def test_sl_tp_calculation(self):
        """SL/TP should be ATR-based and correctly oriented."""
        import importlib
        mod = importlib.import_module("unified_engine")
        rm = mod.RiskManager()
        sl, tp = rm.calculate_sl_tp(price=1.0850, atr=0.005, action="BUY")
        assert sl < 1.0850  # SL below entry for BUY
        assert tp > 1.0850  # TP above entry for BUY

        sl, tp = rm.calculate_sl_tp(price=1.0850, atr=0.005, action="SELL")
        assert sl > 1.0850  # SL above entry for SELL
        assert tp < 1.0850  # TP below entry for SELL

    def test_can_trade_today(self):
        """can_trade_today should return True when limits not hit."""
        import importlib
        mod = importlib.import_module("unified_engine")
        rm = mod.RiskManager()
        assert rm.can_trade_today() is True

    def test_get_state_returns_dict(self):
        """get_state should return a dictionary with risk metrics."""
        import importlib
        mod = importlib.import_module("unified_engine")
        rm = mod.RiskManager()
        state = rm.get_state()
        assert "balance" in state
        assert "drawdown_pct" in state
        assert "circuit_breaker" in state
        assert "total_trades" in state


class TestDeprecatedRiskManager:
    """Test that execution/risk_manager.py is marked deprecated."""

    def test_old_risk_manager_has_deprecation_warning(self):
        """execution/risk_manager.py should have deprecation warning."""
        from pathlib import Path
        rm_path = Path(__file__).parent.parent.parent / "execution" / "risk_manager.py"
        content = rm_path.read_text(encoding="utf-8")
        assert "deprecated" in content.lower() or "DeprecationWarning" in content

    def test_old_risk_manager_docstring_mentions_unified(self):
        """execution/risk_manager.py docstring should point to unified_engine."""
        from pathlib import Path
        rm_path = Path(__file__).parent.parent.parent / "execution" / "risk_manager.py"
        content = rm_path.read_text(encoding="utf-8")
        assert "unified_engine" in content.lower()
