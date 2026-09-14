"""Tests for circuit breaker breakeven bug fix.

Bug: record_trade_result treats pnl=0 as a loss (pnl <= 0), causing
consecutive_losses to increment on breakeven trades. After 3 breakeven
trades, the circuit breaker opens even though no real losses occurred.

Fix: Three-way branch — pnl < 0 = loss, pnl > 0 = win, pnl == 0 = no-op
for win/loss streaks.
"""

import pytest


@pytest.fixture
def risk_manager():
    import importlib
    mod = importlib.import_module("unified_engine")
    return mod.RiskManager()


class TestBreakevenTradeNotCountedAsLoss:
    """Breakeven trades (pnl=0) should not count as losses."""

    def test_breakeven_does_not_increment_losses(self, risk_manager):
        """3 breakeven trades should NOT trigger the circuit breaker."""
        for _ in range(3):
            risk_manager.record_trade_result(0.0, 0.0)
        assert risk_manager.consecutive_losses == 0
        assert risk_manager.circuit_breaker_state == "CLOSED"

    def test_breakeven_does_not_increment_wins(self, risk_manager):
        """Breakeven trades should NOT count as wins either."""
        risk_manager.record_trade_result(0.0, 0.0)
        assert risk_manager.consecutive_wins == 0
        assert risk_manager.consecutive_losses == 0

    def test_breakeven_preserves_loss_streak(self, risk_manager):
        """A breakeven trade between losses should NOT break the streak."""
        risk_manager.record_trade_result(-10.0, -0.001)
        risk_manager.record_trade_result(-10.0, -0.001)
        assert risk_manager.consecutive_losses == 2
        # Breakeven in between — streak should remain
        risk_manager.record_trade_result(0.0, 0.0)
        assert risk_manager.consecutive_losses == 2
        assert risk_manager.circuit_breaker_state == "CLOSED"

    def test_breakeven_preserves_win_streak(self, risk_manager):
        """A breakeven trade between wins should NOT break the streak."""
        risk_manager.record_trade_result(10.0, 0.001)
        risk_manager.record_trade_result(10.0, 0.001)
        assert risk_manager.consecutive_wins == 2
        risk_manager.record_trade_result(0.0, 0.0)
        assert risk_manager.consecutive_wins == 2

    def test_breakeven_does_not_affect_circuit_breaker_recovery(self, risk_manager):
        """Breakeven trade during HALF_OPEN should NOT count as recovery."""
        # Open circuit breaker
        for _ in range(3):
            risk_manager.record_trade_result(-10.0, -0.001)
        assert risk_manager.circuit_breaker_state == "OPEN"
        # Force transition to HALF_OPEN by setting cb_opened_at to past
        from datetime import datetime, timezone, timedelta
        risk_manager.cb_opened_at = datetime.now(timezone.utc) - timedelta(hours=2)
        # First check_circuit_breaker call transitions to HALF_OPEN
        assert risk_manager.check_circuit_breaker() is True
        assert risk_manager.circuit_breaker_state == "HALF_OPEN"
        # Breakeven should NOT count as a recovery
        risk_manager.record_trade_result(0.0, 0.0)
        assert risk_manager.cb_recoveries == 0
        assert risk_manager.circuit_breaker_state == "HALF_OPEN"


class TestRealLossStillTriggersCB:
    """Real losses (pnl < 0) should still trigger the circuit breaker."""

    def test_three_losses_open_cb(self, risk_manager):
        for _ in range(3):
            risk_manager.record_trade_result(-10.0, -0.001)
        assert risk_manager.consecutive_losses == 3
        assert risk_manager.circuit_breaker_state == "OPEN"

    def test_two_losses_then_breakeven_then_loss_opens_cb(self, risk_manager):
        """2 losses + breakeven + 1 loss = 3 real losses → OPEN."""
        risk_manager.record_trade_result(-10.0, -0.001)
        risk_manager.record_trade_result(-10.0, -0.001)
        risk_manager.record_trade_result(0.0, 0.0)  # breakeven
        risk_manager.record_trade_result(-10.0, -0.001)
        assert risk_manager.consecutive_losses == 3
        assert risk_manager.circuit_breaker_state == "OPEN"


class TestRealWinResetsStreak:
    """Wins (pnl > 0) should reset loss streak."""

    def test_win_resets_loss_streak(self, risk_manager):
        risk_manager.record_trade_result(-10.0, -0.001)
        risk_manager.record_trade_result(-10.0, -0.001)
        assert risk_manager.consecutive_losses == 2
        risk_manager.record_trade_result(10.0, 0.001)
        assert risk_manager.consecutive_losses == 0
        assert risk_manager.consecutive_wins == 1
