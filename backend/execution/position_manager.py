import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from backend.django_app.models import Position, Trade
from backend.execution.broker import (
    BaseBroker,
    BrokerFill,
    BrokerPosition,
    OrderSide,
    OrderType,
)
from backend.execution.risk_manager import RiskManager

logger = logging.getLogger(__name__)


class PositionManager:
    def __init__(self, broker: BaseBroker, risk_manager: RiskManager):
        self.broker = broker
        self.risk = risk_manager

    def _build_broker_position_map(self) -> Dict[str, BrokerPosition]:
        positions = self.broker.get_positions()
        return {p.symbol: p for p in positions}

    def _determine_side(self, quantity: Decimal) -> str:
        return Trade.Side.BUY if quantity > 0 else Trade.Side.SELL

    def _abs_quantity(self, quantity: Decimal) -> Decimal:
        return abs(quantity)

    def _calculate_unrealized_pnl(
        self, side: str, entry_price: Decimal, current_price: Decimal, quantity: Decimal
    ) -> Decimal:
        if side == Trade.Side.BUY:
            return (current_price - entry_price) * quantity
        return (entry_price - current_price) * quantity

    @transaction.atomic
    def sync_positions(self, user) -> List[Position]:
        """Sync broker positions with database."""
        broker_map = self._build_broker_position_map()
        existing = {
            p.ticker: p
            for p in Position.objects.filter(user=user)
        }
        synced: List[Position] = []

        for symbol, bp in broker_map.items():
            side = self._determine_side(bp.quantity)
            abs_qty = self._abs_quantity(bp.quantity)
            unrealized = self._calculate_unrealized_pnl(
                side, bp.open_price, bp.current_price, abs_qty
            )

            if symbol in existing:
                pos = existing[symbol]
                pos.quantity = abs_qty
                pos.avg_entry_price = bp.open_price
                pos.current_price = bp.current_price
                pos.unrealized_pnl = unrealized
                pos.save(update_fields=[
                    "quantity", "avg_entry_price", "current_price",
                    "unrealized_pnl", "updated_at",
                ])
            else:
                pos = Position.objects.create(
                    user=user,
                    ticker=symbol,
                    quantity=abs_qty,
                    avg_entry_price=bp.open_price,
                    current_price=bp.current_price,
                    unrealized_pnl=unrealized,
                )
            synced.append(pos)

        broker_symbols = set(broker_map.keys())
        stale = [sym for sym in existing if sym not in broker_symbols]
        if stale:
            Position.objects.filter(user=user, ticker__in=stale).delete()

        return synced

    @transaction.atomic
    def update_pnl(self, user) -> List[Position]:
        """Update P&L for all open positions from broker data."""
        broker_map = self._build_broker_position_map()
        positions = list(Position.objects.filter(user=user))
        updated: List[Position] = []

        for pos in positions:
            bp = broker_map.get(pos.ticker)
            if bp is None:
                continue
            side = self._determine_side(bp.quantity)
            unrealized = self._calculate_unrealized_pnl(
                side, bp.open_price, bp.current_price, pos.quantity
            )
            pos.current_price = bp.current_price
            pos.unrealized_pnl = unrealized
            pos.save(update_fields=[
                "current_price", "unrealized_pnl", "updated_at",
            ])
            updated.append(pos)

        return updated

    @transaction.atomic
    def close_position(
        self, position: Position, quantity: Optional[Decimal] = None
    ) -> Optional[Trade]:
        """Close a position (full or partial)."""
        broker_map = self._build_broker_position_map()
        bp = broker_map.get(position.ticker)
        if bp is None:
            logger.warning("No broker position found for %s", position.ticker)
            return None

        close_qty = quantity if quantity is not None else position.quantity
        if close_qty <= 0 or close_qty > position.quantity:
            logger.warning(
                "Invalid close quantity %s for position %s (has %s)",
                close_qty, position.ticker, position.quantity,
            )
            return None

        try:
            fill = self.broker.close_position(bp.ticket, close_qty)
        except Exception as e:
            logger.error("Broker close failed for %s: %s", position.ticker, e)
            return None

        realized_pnl = self._calculate_realized_pnl(bp, fill)
        self.risk.update_daily_pnl(realized_pnl)
        self.risk.increment_daily_trades()

        side = self._determine_side(bp.quantity)
        close_side = Trade.Side.SELL if side == Trade.Side.BUY else Trade.Side.BUY

        trade = Trade.objects.create(
            user=position.user,
            ticker=position.ticker,
            side=close_side,
            order_type=Trade.OrderType.MARKET,
            quantity=close_qty,
            price=fill.price,
            broker_order_id=fill.broker_order_id,
            filled_quantity=close_qty,
            fill_price=fill.price,
            commission=fill.commission,
            slippage=fill.slippage,
            pnl=realized_pnl,
            status=Trade.Status.EXECUTED,
            executed_at=fill.timestamp,
        )

        remaining = position.quantity - close_qty
        if remaining <= 0:
            position.delete()
        else:
            position.quantity = remaining
            position.current_price = fill.price
            position.unrealized_pnl = self._calculate_unrealized_pnl(
                side, position.avg_entry_price, fill.price, remaining
            )
            position.save(update_fields=[
                "quantity", "current_price", "unrealized_pnl", "updated_at",
            ])

        return trade

    def _calculate_realized_pnl(self, bp: BrokerPosition, fill: BrokerFill) -> Decimal:
        side = self._determine_side(bp.quantity)
        close_qty = fill.quantity
        if side == Trade.Side.BUY:
            pnl = (fill.price - bp.open_price) * close_qty
        else:
            pnl = (bp.open_price - fill.price) * close_qty
        return pnl - fill.commission

    @transaction.atomic
    def close_all_positions(self, user) -> List[Trade]:
        """Close all open positions for a user."""
        positions = list(Position.objects.filter(user=user))
        trades: List[Trade] = []

        for pos in positions:
            trade = self.close_position(pos)
            if trade is not None:
                trades.append(trade)

        return trades

    def apply_trailing_stop(
        self, position: Position, trail_distance_pips: Decimal = Decimal("20")
    ) -> bool:
        """Update trailing stop if price moved favorably."""
        broker_map = self._build_broker_position_map()
        bp = broker_map.get(position.ticker)
        if bp is None:
            return False

        tick_value = self._get_pip_value(bp.symbol)
        if tick_value <= 0:
            return False

        trail_distance = trail_distance_pips * tick_value
        side = self._determine_side(bp.quantity)

        if side == Trade.Side.BUY:
            new_stop = (bp.current_price - trail_distance).quantize(
                Decimal("0.000001"), rounding=ROUND_HALF_UP
            )
            if bp.stop_loss is not None and new_stop <= bp.stop_loss:
                return False
            new_stop = max(new_stop, bp.stop_loss or Decimal("0"))
            if new_stop <= 0:
                return False
        else:
            new_stop = (bp.current_price + trail_distance).quantize(
                Decimal("0.000001"), rounding=ROUND_HALF_UP
            )
            if bp.stop_loss is not None and new_stop >= bp.stop_loss:
                return False
            new_stop = min(new_stop, bp.stop_loss or Decimal("999999"))

        try:
            modified = self.broker.modify_position(bp.ticket, stop_loss=new_stop)
            if modified:
                logger.info(
                    "Trailing stop updated for %s: %s -> %s",
                    position.ticker, bp.stop_loss, new_stop,
                )
            return modified
        except Exception as e:
            logger.error("Failed to update trailing stop for %s: %s", position.ticker, e)
            return False

    def _get_pip_value(self, symbol: str) -> Decimal:
        sym_upper = symbol.upper()
        if "JPY" in sym_upper:
            return Decimal("0.01")
        return Decimal("0.0001")

    @transaction.atomic
    def check_risk_exits(self, user) -> List[Trade]:
        """Check all positions for SL/TP hits and apply trailing stops."""
        broker_map = self._build_broker_position_map()
        positions = list(Position.objects.filter(user=user))
        trades: List[Trade] = []

        for pos in positions:
            bp = broker_map.get(pos.ticker)
            if bp is None:
                continue

            sl_price = self.risk.enforce_stop_loss(bp)
            if sl_price is not None:
                trade = self.close_position(pos)
                if trade is not None:
                    trade.notes = "Stop-loss hit"
                    trade.save(update_fields=["notes"])
                    trades.append(trade)
                continue

            tp_price = self.risk.enforce_take_profit(bp)
            if tp_price is not None:
                trade = self.close_position(pos)
                if trade is not None:
                    trade.notes = "Take-profit hit"
                    trade.save(update_fields=["notes"])
                    trades.append(trade)
                continue

            self.apply_trailing_stop(pos)

        return trades

    def get_position_summary(self, user) -> dict:
        """Summary: total positions, total P&L, per-position details."""
        positions = list(Position.objects.filter(user=user))

        total_pnl = Decimal("0")
        details = []

        for pos in positions:
            total_pnl += pos.unrealized_pnl
            details.append({
                "ticker": pos.ticker,
                "quantity": str(pos.quantity),
                "avg_entry_price": str(pos.avg_entry_price),
                "current_price": str(pos.current_price),
                "unrealized_pnl": str(pos.unrealized_pnl),
                "pnl_percent": (
                    str(
                        (pos.unrealized_pnl / (pos.avg_entry_price * pos.quantity) * Decimal("100")).quantize(
                            Decimal("0.01"), rounding=ROUND_HALF_UP
                        )
                    )
                    if pos.avg_entry_price > 0 and pos.quantity > 0
                    else "0.00"
                ),
            })

        return {
            "total_positions": len(positions),
            "total_unrealized_pnl": str(total_pnl),
            "positions": details,
        }
