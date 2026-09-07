"""Tests for BrokerHealthMonitor."""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest


class TestBrokerHealthMonitor:
    """Tests for the BrokerHealthMonitor class."""

    def _make_broker(self, connected=True, balance=Decimal("10000"), equity=Decimal("10000"),
                     free_margin=Decimal("8000"), profit=Decimal("0"), leverage=100,
                     currency="USD", account_type="standard", margin=Decimal("2000")):
        broker = MagicMock()
        broker.is_connected.return_value = connected
        broker.get_account_info.return_value = MagicMock(
            account_number="12345678",
            balance=balance,
            equity=equity,
            margin=margin,
            free_margin=free_margin,
            leverage=leverage,
            currency=currency,
            account_type=account_type,
            profit=profit,
        )
        return broker

    def test_healthy_when_connected(self):
        from execution.health import BrokerHealthMonitor
        broker = self._make_broker()
        health = BrokerHealthMonitor(broker).check()
        assert health["status"] == "healthy"
        assert health["connected"] is True
        assert health["balance"] == "10000"
        assert health["equity"] == "10000"

    def test_unhealthy_when_disconnected(self):
        from execution.health import BrokerHealthMonitor
        broker = self._make_broker(connected=False)
        health = BrokerHealthMonitor(broker).check()
        assert health["status"] == "disconnected"
        assert health["connected"] is False

    def test_warning_on_high_drawdown(self):
        from execution.health import BrokerHealthMonitor
        # balance=10000, equity=8400 -> drawdown=1600 -> 16% > 15% -> warning
        # free_margin=2000 -> 20% > 10% (not critical)
        broker = self._make_broker(
            balance=Decimal("10000"), equity=Decimal("8400"),
            free_margin=Decimal("2000"), profit=Decimal("-1600"),
        )
        health = BrokerHealthMonitor(broker).check()
        assert health["drawdown_pct"] > 15.0
        assert health["status"] == "warning"

    def test_critical_on_low_free_margin(self):
        from execution.health import BrokerHealthMonitor
        # balance=10000, free_margin=500 -> 5% < 10% -> critical
        broker = self._make_broker(
            balance=Decimal("10000"), equity=Decimal("9500"),
            free_margin=Decimal("500"), profit=Decimal("-500"),
        )
        health = BrokerHealthMonitor(broker).check()
        assert health["free_margin_pct"] < 10
        assert health["status"] == "critical"

    def test_drawdown_pct_calculation(self):
        from execution.health import BrokerHealthMonitor
        # balance=10000, equity=9000 -> 10% drawdown
        broker = self._make_broker(
            balance=Decimal("10000"), equity=Decimal("9000"),
            free_margin=Decimal("6000"), profit=Decimal("-1000"),
        )
        health = BrokerHealthMonitor(broker).check()
        assert abs(health["drawdown_pct"] - 10.0) < 0.01

    def test_free_margin_pct_calculation(self):
        from execution.health import BrokerHealthMonitor
        # balance=10000, free_margin=5000 -> 50%
        broker = self._make_broker(
            balance=Decimal("10000"), equity=Decimal("10000"),
            free_margin=Decimal("5000"), profit=Decimal("0"),
        )
        health = BrokerHealthMonitor(broker).check()
        assert abs(health["free_margin_pct"] - 50.0) < 0.01

    def test_zero_balance_no_division_error(self):
        from execution.health import BrokerHealthMonitor
        broker = self._make_broker(
            balance=Decimal("0"), equity=Decimal("0"),
            free_margin=Decimal("0"), profit=Decimal("0"),
        )
        health = BrokerHealthMonitor(broker).check()
        assert health["drawdown_pct"] == 0.0
        assert health["free_margin_pct"] == 0.0

    def test_includes_leverage_and_currency(self):
        from execution.health import BrokerHealthMonitor
        broker = self._make_broker(leverage=500, currency="EUR")
        health = BrokerHealthMonitor(broker).check()
        assert health["leverage"] == 500
        assert health["currency"] == "EUR"

    def test_profit_included_in_result(self):
        from execution.health import BrokerHealthMonitor
        broker = self._make_broker(profit=Decimal("250.50"))
        health = BrokerHealthMonitor(broker).check()
        assert health["profit"] == "250.50"
