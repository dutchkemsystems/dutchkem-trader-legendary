import logging
from datetime import timedelta, timezone as _tz
from decimal import Decimal
from typing import Optional

try:
    from django.contrib.auth.models import User
except Exception:
    User = type("User", (), {"__init__": lambda *a, **kw: None})

try:
    from django.db import transaction
except Exception:
    from contextlib import contextmanager as _ctx

    transaction = type("transaction", (), {"atomic": _ctx(lambda: (yield))})()

try:
    from django.db.models import Sum
except Exception:

    def Sum(field):
        return field


try:
    from django.utils import timezone
except Exception:

    class timezone:
        @staticmethod
        def now():
            from datetime import datetime

            return datetime.now(_tz.utc)

        @staticmethod
        def utc():
            return _tz.utc


from django_app.models import ConsensusResult, Trade
from execution.account import AccountManager
from execution.broker import (
    BaseBroker,
    BrokerOrder,
    OrderSide,
    OrderType,
)
from execution.position_manager import PositionManager
from execution.position_sizer import PositionSizer
from execution.risk_manager import RiskManager

logger = logging.getLogger(__name__)


class OrderExecutionEngine:
    """Main orchestrator for trade execution.

    Wires together AccountManager, PositionSizer, RiskManager, and
    PositionManager to provide a single entry point for placing and
    managing trades through the broker.
    """

    def __init__(self, broker: BaseBroker):
        self.broker = broker
        self.account = AccountManager(broker)
        self.sizer = PositionSizer(self.account)
        self.risk = RiskManager(self.account)
        self.positions = PositionManager(broker, self.risk)

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def initialize(self, user: User, force_account_type: Optional[str] = None) -> dict:
        """Initialize engine for a user. Returns connection status."""
        config = self.account.initialize(user, force_type=force_account_type)
        self.positions.sync_positions(user)

        return {
            "connected": self.broker.is_connected(),
            "account_number": config.account_number,
            "account_type": config.account_type,
            "balance": str(config.balance),
            "equity": str(config.equity),
            "free_margin": str(config.free_margin),
            "leverage": config.leverage,
            "currency": config.currency,
            "is_cent": self.account.is_cent_account(),
            "open_positions": 0,
        }

    # ------------------------------------------------------------------
    # Trade execution pipeline
    # ------------------------------------------------------------------

    def execute_trade(
        self,
        user: User,
        symbol: str,
        side: str,
        lot_size: Optional[Decimal] = None,
        entry_price: Optional[Decimal] = None,
        stop_loss: Optional[Decimal] = None,
        take_profit: Optional[Decimal] = None,
        order_type: str = "MARKET",
        confidence: Optional[float] = None,
        consensus_id: Optional[str] = None,
    ) -> Trade:
        """Execute a trade with full risk validation.

        Pipeline:
        1. Get current price if not provided
        2. Auto-calculate stops if not provided
        3. Auto-calculate lot size if not provided (using confidence)
        4. Create BrokerOrder
        5. Validate with RiskManager
        6. Create pending Trade record
        7. Place order with broker
        8. Update Trade with fill info
        9. Update Position
        10. Increment daily trade counter
        """

        # 1. Get current price if not provided
        if entry_price is None:
            tick = self.broker.get_tick(symbol)
            if side.upper() == "BUY":
                entry_price = tick["ask"]
            else:
                entry_price = tick["bid"]

        # 2. Auto-calculate stops if not provided
        if stop_loss is None:
            stop_loss = self.sizer.calculate_dynamic_stop_loss(
                entry_price, side, symbol=symbol
            )
        if take_profit is None:
            take_profit = self.sizer.calculate_take_profit(entry_price, stop_loss, side)

        # 3. Auto-calculate lot size if not provided
        if lot_size is None:
            if confidence is not None:
                lot_size = self.sizer.calculate_lot_size_from_confidence(
                    entry_price, stop_loss, confidence, symbol
                )
            else:
                lot_size = self.sizer.calculate_lot_size(
                    entry_price, stop_loss, symbol=symbol
                )

        # 4. Create BrokerOrder
        broker_order = BrokerOrder(
            symbol=symbol,
            side=OrderSide(side.upper()),
            order_type=OrderType(order_type.upper()),
            quantity=lot_size,
            price=entry_price if order_type.upper() != "MARKET" else None,
            stop_loss=stop_loss,
            take_profit=take_profit,
            comment="dutchkem",
        )

        # 5. Validate with RiskManager
        valid, message = self.risk.validate_trade(broker_order, lot_size, entry_price)
        if not valid:
            trade = Trade.objects.create(
                user=user,
                ticker=symbol,
                side=side.upper(),
                order_type=order_type.upper(),
                quantity=lot_size,
                price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                status=Trade.Status.FAILED,
                notes=f"Risk validation failed: {message}",
            )
            return trade

        # 6. Create pending Trade record
        consensus = None
        if consensus_id:
            try:
                consensus = ConsensusResult.objects.get(id=consensus_id)
            except ConsensusResult.DoesNotExist:
                pass

        trade = Trade.objects.create(
            user=user,
            ticker=symbol,
            side=side.upper(),
            order_type=order_type.upper(),
            quantity=lot_size,
            price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            consensus=consensus,
            status=Trade.Status.SUBMITTED,
        )

        # 7. Place order with broker
        try:
            fill = self.broker.place_order(broker_order)
        except Exception as e:
            trade.status = Trade.Status.FAILED
            trade.notes = f"Broker error: {e}"
            trade.save(update_fields=["status", "notes"])
            logger.error("Broker order failed for %s: %s", symbol, e)
            return trade

        # 8. Update Trade with fill info
        trade.broker_order_id = fill.broker_order_id
        trade.filled_quantity = fill.quantity
        trade.fill_price = fill.price
        trade.commission = fill.commission
        trade.slippage = fill.slippage
        trade.status = Trade.Status.EXECUTED
        trade.executed_at = fill.timestamp
        trade.save()

        # 9. Update Position (sync after fill)
        self.positions.sync_positions(user)

        # 10. Increment daily trade counter
        self.risk.increment_daily_trades()

        logger.info(
            "Trade executed: %s %s %s @ %s (fill=%s, slippage=%s)",
            trade.side,
            trade.quantity,
            trade.ticker,
            trade.price,
            trade.fill_price,
            trade.slippage,
        )

        return trade

    # ------------------------------------------------------------------
    # Close trade
    # ------------------------------------------------------------------

    def close_trade(self, trade_id: str, user: User) -> Optional[Trade]:
        """Close an open position by its trade ID."""
        try:
            trade = Trade.objects.get(id=trade_id, user=user)
        except Trade.DoesNotExist:
            logger.warning("Trade %s not found for user %s", trade_id, user.id)
            return None

        positions = list(
            PositionManager(broker=self.broker, risk_manager=self.risk).sync_positions(
                user
            )
        )

        from django_app.models import Position

        position = Position.objects.filter(user=user, ticker=trade.ticker).first()
        if position is None:
            logger.warning("No open position for %s", trade.ticker)
            return None

        return self.positions.close_position(position)

    # ------------------------------------------------------------------
    # History & summaries
    # ------------------------------------------------------------------

    def get_trade_history(self, user: User, limit: int = 50) -> list:
        """Return recent trades for a user."""
        trades = Trade.objects.filter(user=user).order_by("-created_at")[:limit]
        return [
            {
                "id": str(t.id),
                "symbol": t.ticker,
                "action": t.side,
                "order_type": t.order_type,
                "lot_size": float(t.quantity),
                "entry_price": float(t.price),
                "stop_loss": float(t.stop_loss) if t.stop_loss else None,
                "take_profit": float(t.take_profit) if t.take_profit else None,
                "fill_price": float(t.fill_price) if t.fill_price else None,
                "pnl": float(t.pnl),
                "commission": float(t.commission),
                "slippage": float(t.slippage),
                "status": t.status,
                "notes": t.notes,
                "executed_at": t.executed_at.isoformat() if t.executed_at else None,
                "created_at": t.created_at.isoformat(),
            }
            for t in trades
        ]

    def get_daily_summary(self, user: User) -> dict:
        """Return today's trading summary."""
        today = timezone.now().date()
        start = timezone.make_aware(
            timezone.datetime.combine(today, timezone.datetime.min.time())
        )
        trades = Trade.objects.filter(user=user, created_at__gte=start).order_by(
            "-created_at"
        )

        executed = trades.filter(status=Trade.Status.EXECUTED)
        total_pnl = executed.aggregate(total=Sum("pnl"))["total"] or Decimal("0")
        total_commission = executed.aggregate(total=Sum("commission"))[
            "total"
        ] or Decimal("0")

        return {
            "date": today.isoformat(),
            "total_trades": trades.count(),
            "executed_trades": executed.count(),
            "total_pnl": str(total_pnl),
            "total_commission": str(total_commission),
            "net_pnl": str(total_pnl - total_commission),
            "risk_status": self.risk.get_risk_status(),
        }

    def get_monthly_summary(self, user: User) -> dict:
        """Return this month's trading summary."""
        today = timezone.now().date()
        start = today.replace(day=1)
        start_dt = timezone.make_aware(
            timezone.datetime.combine(start, timezone.datetime.min.time())
        )
        trades = Trade.objects.filter(user=user, created_at__gte=start_dt).order_by(
            "-created_at"
        )

        executed = trades.filter(status=Trade.Status.EXECUTED)
        total_pnl = executed.aggregate(total=Sum("pnl"))["total"] or Decimal("0")
        total_commission = executed.aggregate(total=Sum("commission"))[
            "total"
        ] or Decimal("0")

        wins = executed.filter(pnl__gt=0).count()
        losses = executed.filter(pnl__lt=0).count()
        win_rate = (
            (wins / (wins + losses) * 100) if (wins + losses) > 0 else Decimal("0")
        )

        return {
            "month": start.isoformat()[:7],
            "total_trades": trades.count(),
            "executed_trades": executed.count(),
            "wins": wins,
            "losses": losses,
            "win_rate": str(round(win_rate, 2)),
            "total_pnl": str(total_pnl),
            "total_commission": str(total_commission),
            "net_pnl": str(total_pnl - total_commission),
        }
