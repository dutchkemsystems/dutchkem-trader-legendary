from decimal import Decimal
from typing import Optional, Tuple

from backend.django_app.models import Position
from backend.execution.broker import BrokerOrder, OrderSide
from backend.execution.account import AccountManager


class RiskManager:
    MAX_RISK_PER_TRADE = Decimal("2.0")
    DAILY_LOSS_LIMIT = Decimal("5.0")
    MAX_OPEN_POSITIONS = 10
    MAX_POSITION_SIZE_PERCENT = Decimal("10.0")
    MAX_DAILY_TRADES = 20
    MAX_DRAWDOWN_PERCENT = Decimal("15.0")

    def __init__(self, account_manager: AccountManager):
        self.account = account_manager
        self._peak_balance = Decimal("0")
        self._daily_pnl = Decimal("0")
        self._daily_trades = 0

    def _get_balance(self) -> Decimal:
        config = self.account.get_config()
        if config is None:
            return Decimal("0")
        return Decimal(str(config.balance))

    def _get_equity(self) -> Decimal:
        config = self.account.get_config()
        if config is None:
            return Decimal("0")
        return Decimal(str(config.equity))

    def validate_trade(
        self, order: BrokerOrder, lot_size: Decimal, entry_price: Decimal
    ) -> Tuple[bool, str]:
        balance = self._get_balance()

        # 1. Daily loss limit
        if balance > 0 and self._daily_pnl < 0:
            loss_pct = abs(self._daily_pnl) / balance * Decimal("100")
            if loss_pct >= self.DAILY_LOSS_LIMIT:
                return False, f"Daily loss limit reached ({loss_pct:.1f}% >= {self.DAILY_LOSS_LIMIT}%)"

        # 2. Max open positions
        open_count = Position.objects.count()
        if open_count >= self.MAX_OPEN_POSITIONS:
            return False, f"Max open positions reached ({open_count} >= {self.MAX_OPEN_POSITIONS})"

        # 3. Max daily trades
        if self._daily_trades >= self.MAX_DAILY_TRADES:
            return False, f"Max daily trades reached ({self._daily_trades} >= {self.MAX_DAILY_TRADES})"

        # 4. Position size limit
        if balance > 0:
            position_value = lot_size * entry_price
            size_pct = position_value / balance * Decimal("100")
            if size_pct > self.MAX_POSITION_SIZE_PERCENT:
                return False, f"Position size too large ({size_pct:.1f}% > {self.MAX_POSITION_SIZE_PERCENT}%)"

        # 5. Max drawdown
        equity = self._get_equity()
        if self._peak_balance > 0 and equity > 0:
            if equity > self._peak_balance:
                self._peak_balance = equity
            drawdown_pct = (self._peak_balance - equity) / self._peak_balance * Decimal("100")
            if drawdown_pct >= self.MAX_DRAWDOWN_PERCENT:
                return False, f"Max drawdown reached ({drawdown_pct:.1f}% >= {self.MAX_DRAWDOWN_PERCENT}%)"

        # 6. Risk per trade (requires stop-loss)
        if order.stop_loss is None:
            return False, "Stop-loss is required for risk management"
        if balance > 0 and entry_price > 0 and lot_size > 0:
            if order.side == OrderSide.BUY:
                risk_per_unit = entry_price - order.stop_loss
            else:
                risk_per_unit = order.stop_loss - entry_price
            if risk_per_unit <= 0:
                return False, "Invalid stop-loss: no risk buffer"
            total_risk = risk_per_unit * lot_size
            risk_pct = total_risk / balance * Decimal("100")
            if risk_pct > self.MAX_RISK_PER_TRADE:
                return False, f"Risk per trade too high ({risk_pct:.1f}% > {self.MAX_RISK_PER_TRADE}%)"

        return True, "All risk checks passed"

    def update_daily_pnl(self, pnl: Decimal):
        self._daily_pnl += pnl

    def increment_daily_trades(self):
        self._daily_trades += 1

    def reset_daily(self):
        self._daily_pnl = Decimal("0")
        self._daily_trades = 0

    def get_risk_status(self) -> dict:
        balance = self._get_balance()
        equity = self._get_equity()
        drawdown_pct = Decimal("0")
        if self._peak_balance > 0 and equity > 0:
            drawdown_pct = (self._peak_balance - equity) / self._peak_balance * Decimal("100")
        return {
            "daily_pnl": str(self._daily_pnl),
            "daily_trades": self._daily_trades,
            "peak_balance": str(self._peak_balance),
            "drawdown_pct": str(drawdown_pct),
            "max_drawdown_pct": str(self.MAX_DRAWDOWN_PERCENT),
            "open_positions": Position.objects.count(),
            "max_open_positions": self.MAX_OPEN_POSITIONS,
            "daily_loss_limit_pct": str(self.DAILY_LOSS_LIMIT),
            "max_daily_trades": self.MAX_DAILY_TRADES,
        }

    def enforce_stop_loss(self, position) -> Optional[Decimal]:
        current_price = Decimal(str(position.current_price))
        stop_loss = getattr(position, "stop_loss", None)
        if stop_loss is None:
            return None
        stop_loss = Decimal(str(stop_loss))
        if position.side == "BUY" and current_price <= stop_loss:
            return current_price
        if position.side == "SELL" and current_price >= stop_loss:
            return current_price
        return None

    def enforce_take_profit(self, position) -> Optional[Decimal]:
        current_price = Decimal(str(position.current_price))
        take_profit = getattr(position, "take_profit", None)
        if take_profit is None:
            return None
        take_profit = Decimal(str(take_profit))
        if position.side == "BUY" and current_price >= take_profit:
            return current_price
        if position.side == "SELL" and current_price <= take_profit:
            return current_price
        return None
