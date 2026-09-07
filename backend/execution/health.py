"""Broker health monitoring — checks connection status and account risk metrics."""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict

from execution.broker import BaseBroker


class BrokerHealthMonitor:
    """Monitor broker connection health and account risk metrics."""

    DRAWDOWN_WARNING_PCT = 15.0
    FREE_MARGIN_CRITICAL_PCT = 10.0

    def __init__(self, broker: BaseBroker) -> None:
        self._broker = broker

    def check(self) -> Dict[str, Any]:
        if not self._broker.is_connected():
            return {"status": "disconnected", "connected": False}

        info = self._broker.get_account_info()
        balance = info.balance or Decimal("0")
        equity = info.equity or Decimal("0")
        free_margin = info.free_margin or Decimal("0")
        profit = info.profit or Decimal("0")

        if balance > 0:
            drawdown = balance - equity if balance > equity else Decimal("0")
            drawdown_pct = float(drawdown / balance * 100)
            free_margin_pct = float(free_margin / balance * 100)
        else:
            drawdown_pct = 0.0
            free_margin_pct = 0.0

        if free_margin_pct < self.FREE_MARGIN_CRITICAL_PCT:
            status = "critical"
        elif drawdown_pct > self.DRAWDOWN_WARNING_PCT:
            status = "warning"
        else:
            status = "healthy"

        return {
            "status": status,
            "connected": True,
            "balance": str(balance),
            "equity": str(equity),
            "free_margin": str(free_margin),
            "profit": str(profit),
            "drawdown_pct": drawdown_pct,
            "free_margin_pct": free_margin_pct,
            "leverage": info.leverage,
            "currency": info.currency,
        }
