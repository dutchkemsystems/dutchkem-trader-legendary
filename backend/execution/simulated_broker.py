"""SimulatedBroker — in-memory broker for backtesting with no Django ORM dependency."""
from __future__ import annotations

import random
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from execution.broker import (
    AccountInfo,
    BaseBroker,
    BrokerFill,
    BrokerOrder,
    BrokerPosition,
    OrderSide,
    OrderType,
)

# Defaults
DEFAULT_BALANCE = Decimal("10000.00")
DEFAULT_LEVERAGE = 100
DEFAULT_CURRENCY = "USD"
DEFAULT_COMMISSION_PER_LOT = Decimal("7.00")
DEFAULT_MAX_SLIPPAGE_PIPS = Decimal("1")
MAX_TICKET = 2_000_000

# Symbol metadata for simulation
_SYMBOL_META: Dict[str, Dict[str, Any]] = {
    "EURUSD": {"digits": 5, "point": Decimal("0.00001"), "spread_pips": Decimal("1.5"), "base": Decimal("1.08500")},
    "GBPUSD": {"digits": 5, "point": Decimal("0.00001"), "spread_pips": Decimal("2.0"), "base": Decimal("1.26500")},
    "USDJPY": {"digits": 3, "point": Decimal("0.001"), "spread_pips": Decimal("1.5"), "base": Decimal("149.500")},
    "AUDUSD": {"digits": 5, "point": Decimal("0.00001"), "spread_pips": Decimal("1.8"), "base": Decimal("0.65200")},
    "USDCAD": {"digits": 5, "point": Decimal("0.00001"), "spread_pips": Decimal("2.0"), "base": Decimal("1.36400")},
    "USDCHF": {"digits": 5, "point": Decimal("0.00001"), "spread_pips": Decimal("1.8"), "base": Decimal("0.87800")},
    "NZDUSD": {"digits": 5, "point": Decimal("0.00001"), "spread_pips": Decimal("2.5"), "base": Decimal("0.59800")},
    "XAUUSD": {"digits": 2, "point": Decimal("0.01"), "spread_pips": Decimal("3.0"), "base": Decimal("2350.00")},
}

_DEFAULT_META = {"digits": 5, "point": Decimal("0.00001"), "spread_pips": Decimal("2.0"), "base": Decimal("1.10000")}

JPY_PAIRS = ("JPY",)


def _pip_size(symbol: str) -> Decimal:
    meta = _SYMBOL_META.get(symbol.upper(), _DEFAULT_META)
    return meta["point"] * Decimal("10") if "JPY" not in symbol.upper() else Decimal("0.01")


def _base_price(symbol: str) -> Decimal:
    meta = _SYMBOL_META.get(symbol.upper(), _DEFAULT_META)
    return meta["base"]


def _spread_for(symbol: str) -> Decimal:
    meta = _SYMBOL_META.get(symbol.upper(), _DEFAULT_META)
    return meta["spread_pips"] * _pip_size(symbol)


class SimulatedBroker(BaseBroker):
    """In-memory broker simulation for backtesting.

    No Django ORM dependency. Provides instant fills with configurable
    slippage and commission. All state is instance-local.

    Args:
        initial_balance: Starting account balance.
        commission_per_lot: Commission charged per standard lot.
        max_slippage_pips: Maximum slippage in pips for market orders.
        spread_pips: Override spread (None = use per-symbol defaults).
    """

    def __init__(
        self,
        initial_balance: Decimal = DEFAULT_BALANCE,
        commission_per_lot: Decimal = DEFAULT_COMMISSION_PER_LOT,
        max_slippage_pips: Decimal = DEFAULT_MAX_SLIPPAGE_PIPS,
        spread_pips: Optional[Decimal] = None,
    ) -> None:
        self._initial_balance = initial_balance
        self._commission_per_lot = commission_per_lot
        self._max_slippage_pips = max_slippage_pips
        self._spread_pips_override = spread_pips

        # Connection state
        self._connected: bool = False
        self._account_number: str = ""
        self._server: str = ""

        # Account state
        self._balance: Decimal = initial_balance
        self._margin: Decimal = Decimal("0.00")
        self._free_margin: Decimal = initial_balance

        # Position state
        self._positions: Dict[int, BrokerPosition] = {}
        self._next_ticket: int = 1

        # Price feed: symbol -> current mid price
        self._prices: Dict[str, Decimal] = {}

        # Trade history
        self._trade_history: List[BrokerFill] = []

    # ------------------------------------------------------------------
    # BaseBroker — connection
    # ------------------------------------------------------------------

    def connect(self, account_number: str, password: str, server: str) -> bool:
        self._connected = True
        self._account_number = account_number or "SIM-000000"
        self._server = server or "Backtest"
        return True

    def disconnect(self) -> None:
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    # ------------------------------------------------------------------
    # BaseBroker — account
    # ------------------------------------------------------------------

    def get_account_info(self) -> AccountInfo:
        equity = self._calculate_equity()
        profit = equity - self._balance - self._margin
        account_type = "CENT" if self._balance < Decimal("1000") else "STANDARD"
        return AccountInfo(
            account_number=self._account_number,
            balance=self._balance,
            equity=equity,
            margin=self._margin,
            free_margin=self._free_margin,
            leverage=DEFAULT_LEVERAGE,
            currency=DEFAULT_CURRENCY,
            account_type=account_type,
            profit=profit,
        )

    def _calculate_equity(self) -> Decimal:
        unrealized = Decimal("0")
        for p in self._positions.values():
            if p.side == OrderSide.BUY:
                unrealized += (p.current_price - p.open_price) * p.quantity
            else:
                unrealized += (p.open_price - p.current_price) * p.quantity
        return self._balance + unrealized

    # ------------------------------------------------------------------
    # BaseBroker — orders
    # ------------------------------------------------------------------

    def place_order(self, order: BrokerOrder) -> BrokerFill:
        if not self._connected:
            raise RuntimeError("Broker not connected")

        if order.order_type == OrderType.MARKET:
            fill_price = self._get_market_fill_price(order)
        elif order.order_type in (OrderType.LIMIT, OrderType.STOP, OrderType.STOP_LIMIT):
            fill_price = order.price
        else:
            raise ValueError(f"Unknown order type: {order.order_type}")

        # Calculate commission
        commission = (self._commission_per_lot * order.quantity).quantize(Decimal("0.01"))

        # Calculate slippage
        pip_size = _pip_size(order.symbol)
        slippage = Decimal("0.00")
        if order.order_type == OrderType.MARKET:
            max_slippage_price = self._max_slippage_pips * pip_size
            slippage = Decimal(str(round(random.uniform(0, float(max_slippage_price)), 6)))
            if order.side == OrderSide.BUY:
                fill_price = fill_price + slippage
            else:
                fill_price = fill_price - slippage

        # Check margin
        required_margin = fill_price * order.quantity / Decimal(str(DEFAULT_LEVERAGE))
        if required_margin > self._free_margin:
            raise RuntimeError(
                f"Insufficient margin: required {required_margin}, available {self._free_margin}"
            )

        # Reserve margin
        self._margin += required_margin
        self._free_margin -= required_margin

        # Create position
        ticket = self._next_ticket
        self._next_ticket += 1

        position = BrokerPosition(
            ticket=ticket,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            open_price=fill_price,
            current_price=fill_price,
            unrealized_pnl=Decimal("0.00"),
            swap=Decimal("0.00"),
            commission=commission,
            open_time=datetime.now(timezone.utc),
            stop_loss=order.stop_loss,
            take_profit=order.take_profit,
            magic_number=order.magic_number,
            comment=order.comment,
        )
        self._positions[ticket] = position

        fill = BrokerFill(
            order_id=str(uuid.uuid4()),
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            price=fill_price,
            commission=commission,
            slippage=slippage,
            timestamp=datetime.now(timezone.utc),
            broker_order_id=str(ticket),
        )
        self._trade_history.append(fill)
        return fill

    def _get_market_fill_price(self, order: BrokerOrder) -> Decimal:
        mid = self._get_mid_price(order.symbol)
        spread = self._get_spread(order.symbol)
        if order.side == OrderSide.BUY:
            return mid + spread / 2
        return mid - spread / 2

    def _get_mid_price(self, symbol: str) -> Decimal:
        if symbol in self._prices:
            return self._prices[symbol]
        return _base_price(symbol)

    def _get_spread(self, symbol: str) -> Decimal:
        if self._spread_pips_override is not None:
            return self._spread_pips_override * _pip_size(symbol)
        return _spread_for(symbol)

    # ------------------------------------------------------------------
    # BaseBroker — position management
    # ------------------------------------------------------------------

    def modify_position(
        self,
        ticket: int,
        stop_loss: Optional[Decimal] = None,
        take_profit: Optional[Decimal] = None,
    ) -> bool:
        pos = self._positions.get(ticket)
        if pos is None:
            return False
        if stop_loss is not None:
            pos.stop_loss = stop_loss
        if take_profit is not None:
            pos.take_profit = take_profit
        return True

    def close_position(
        self, ticket: int, quantity: Optional[Decimal] = None
    ) -> BrokerFill:
        pos = self._positions.get(ticket)
        if pos is None:
            raise RuntimeError(f"Position {ticket} not found")

        close_qty = quantity or pos.quantity
        if close_qty <= 0 or close_qty > pos.quantity:
            raise RuntimeError(
                f"Invalid close quantity {close_qty} for position {ticket} (has {pos.quantity})"
            )

        close_side = OrderSide.SELL if pos.side == OrderSide.BUY else OrderSide.BUY
        pip_size = _pip_size(pos.symbol)
        max_slippage_price = self._max_slippage_pips * pip_size
        slippage = Decimal(str(round(random.uniform(0, float(max_slippage_price)), 6)))

        close_price = pos.current_price
        if close_side == OrderSide.SELL:
            close_price = close_price - slippage
        else:
            close_price = close_price + slippage

        commission = (self._commission_per_lot * close_qty).quantize(Decimal("0.01"))

        # Release margin
        released_margin = pos.open_price * close_qty / Decimal(str(DEFAULT_LEVERAGE))
        self._margin -= released_margin
        self._free_margin += released_margin

        # Calculate realized P&L and update balance
        if pos.side == OrderSide.BUY:
            realized_pnl = (close_price - pos.open_price) * close_qty
        else:
            realized_pnl = (pos.open_price - close_price) * close_qty
        self._balance += realized_pnl

        # Remove or reduce position
        if close_qty >= pos.quantity:
            del self._positions[ticket]
        else:
            pos.quantity -= close_qty

        fill = BrokerFill(
            order_id=str(uuid.uuid4()),
            symbol=pos.symbol,
            side=close_side,
            quantity=close_qty,
            price=close_price,
            commission=commission,
            slippage=slippage,
            timestamp=datetime.now(timezone.utc),
            broker_order_id=str(ticket),
        )
        self._trade_history.append(fill)
        return fill

    # ------------------------------------------------------------------
    # BaseBroker — queries
    # ------------------------------------------------------------------

    def get_positions(self) -> List[BrokerPosition]:
        return list(self._positions.values())

    def get_position(self, ticket: int) -> Optional[BrokerPosition]:
        return self._positions.get(ticket)

    def get_tick(self, symbol: str) -> Dict[str, Any]:
        mid = self._get_mid_price(symbol)
        spread = self._get_spread(symbol)
        return {
            "bid": mid - spread / 2,
            "ask": mid + spread / 2,
            "spread": spread,
            "last": mid,
            "volume": Decimal("0.00"),
            "timestamp": datetime.now(timezone.utc),
        }

    def get_symbol_info(self, symbol: str) -> Dict[str, Any]:
        meta = _SYMBOL_META.get(symbol.upper(), _DEFAULT_META)
        return {
            "symbol": symbol,
            "digits": meta["digits"],
            "point": meta["point"],
            "spread": int(meta["spread_pips"]),
            "volume_min": Decimal("0.01"),
            "volume_max": Decimal("100.00"),
            "volume_step": Decimal("0.01"),
            "trade_contract_size": Decimal("100000"),
            "trade_mode": 0,
            "margin_initial": Decimal("0.00"),
            "margin_maintenance": Decimal("0.00"),
        }

    # ------------------------------------------------------------------
    # SimulatedBroker-specific methods
    # ------------------------------------------------------------------

    def get_trade_history(self) -> List[BrokerFill]:
        """Return list of all fills (opens and closes)."""
        return list(self._trade_history)

    def _update_tick(self, symbol: str, price: Decimal) -> None:
        """Update the simulated mid-price for a symbol.

        Recalculates unrealized P&L for all open positions on this symbol.
        """
        self._prices[symbol] = price
        for pos in self._positions.values():
            if pos.symbol == symbol:
                pos.current_price = price
                if pos.side == OrderSide.BUY:
                    pos.unrealized_pnl = (price - pos.open_price) * pos.quantity
                else:
                    pos.unrealized_pnl = (pos.open_price - price) * pos.quantity
