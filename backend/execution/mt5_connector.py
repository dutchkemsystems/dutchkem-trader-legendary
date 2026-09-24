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
    OrderStatus,
    OrderType,
)

try:
    import MetaTrader5 as mt5

    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False

SIMULATED_BALANCE = Decimal("10000.00")
SIMULATED_LEVERAGE = 100
SIMULATED_CURRENCY = "USD"
_MAX_TICKET = 1_000_000


class MT5Connector(BaseBroker):
    """MetaTrader 5 broker connector with automatic simulation fallback.

    When the ``MetaTrader5`` package is not installed (or import fails),
    every operation runs in a local simulation mode with realistic slippage
    and in-memory position tracking.
    """

    def __init__(self, config=None) -> None:
        from config.broker_config import BrokerConfig
        self._config = config or BrokerConfig()
        self._connected: bool = False
        self._account_number: str = ""
        self._server: str = ""

        # --- simulation state ---
        self._sim_balance: Decimal = SIMULATED_BALANCE
        self._sim_equity: Decimal = SIMULATED_BALANCE
        self._sim_margin: Decimal = Decimal("0.00")
        self._sim_free_margin: Decimal = SIMULATED_BALANCE
        self._sim_positions: Dict[int, BrokerPosition] = {}
        self._sim_pending: Dict[int, Dict] = {}  # Pending orders for sim mode
        self._next_ticket: int = 1

    # ------------------------------------------------------------------
    # BaseBroker interface — connection
    # ------------------------------------------------------------------

    def connect(
        self, account_number: str, password: str, server: str
    ) -> bool:
        if MT5_AVAILABLE:
            if not mt5.initialize():
                return False
            login_result = mt5.login(
                int(account_number), password=password, server=server
            )
            if not login_result:
                mt5.shutdown()
                return False
            self._connected = True
            self._account_number = account_number
            self._server = server
            return True

        # simulation
        self._connected = True
        self._account_number = account_number or "SIM-000000"
        self._server = server or "Simulation"
        return True

    def disconnect(self) -> None:
        if MT5_AVAILABLE and self._connected:
            mt5.shutdown()
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    # ------------------------------------------------------------------
    # Account
    # ------------------------------------------------------------------

    def get_account_info(self) -> AccountInfo:
        if MT5_AVAILABLE and self._connected:
            info = mt5.account_info()
            if info is None:
                raise RuntimeError("Failed to retrieve MT5 account info")
            balance = Decimal(str(info.balance))
            account_type = "CENT" if balance < 1000 else "STANDARD"
            return AccountInfo(
                account_number=str(info.login),
                balance=balance,
                equity=Decimal(str(info.equity)),
                margin=Decimal(str(info.margin)),
                free_margin=Decimal(str(info.margin_free)),
                leverage=info.leverage,
                currency=info.currency,
                account_type=account_type,
                profit=Decimal(str(info.profit)),
            )

        account_type = (
            "CENT" if self._sim_balance < 1000 else "STANDARD"
        )
        return AccountInfo(
            account_number=self._account_number,
            balance=self._sim_balance,
            equity=self._sim_equity,
            margin=self._sim_margin,
            free_margin=self._sim_free_margin,
            leverage=SIMULATED_LEVERAGE,
            currency=SIMULATED_CURRENCY,
            account_type=account_type,
            profit=Decimal("0.00"),
        )

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------

    def place_order(self, order: BrokerOrder) -> BrokerFill:
        if MT5_AVAILABLE and self._connected:
            return self._place_order_real(order)
        return self._place_order_sim(order)

    def _place_order_real(self, order: BrokerOrder) -> BrokerFill:
        symbol = order.symbol
        action = (
            mt5.TRADE_ACTION_DEAL
            if order.order_type == OrderType.MARKET
            else mt5.TRADE_ACTION_PENDING
        )

        price = 0.0
        if order.order_type == OrderType.MARKET:
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                raise RuntimeError(f"Cannot get tick for {symbol}")
            price = (
                tick.ask
                if order.side == OrderSide.BUY
                else tick.bid
            )
        else:
            price = float(order.price)

        mt5_order = {
            "action": action,
            "symbol": symbol,
            "volume": float(order.quantity),
            "type": (
                mt5.ORDER_TYPE_BUY
                if order.side == OrderSide.BUY
                else mt5.ORDER_TYPE_SELL
            ),
            "price": price,
            "deviation": 20,
            "magic": order.magic_number,
            "comment": order.comment or "dutchkem",
        }

        if order.order_type in (OrderType.LIMIT, OrderType.STOP):
            mt5_order["type"] = (
                mt5.ORDER_TYPE_BUY_LIMIT
                if order.order_type == OrderType.LIMIT
                and order.side == OrderSide.BUY
                else mt5.ORDER_TYPE_SELL_LIMIT
                if order.order_type == OrderType.LIMIT
                else mt5.ORDER_TYPE_BUY_STOP
                if order.side == OrderSide.BUY
                else mt5.ORDER_TYPE_SELL_STOP
            )

        if order.stop_loss is not None:
            mt5_order["sl"] = float(order.stop_loss)
        if order.take_profit is not None:
            mt5_order["tp"] = float(order.take_profit)

        result = mt5.order_send(mt5_order)
        if result is None:
            raise RuntimeError("mt5.order_send returned None")
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            raise RuntimeError(
                f"MT5 order failed: {result.comment} "
                f"(code={result.retcode})"
            )

        fill_price = Decimal(str(result.price))
        return BrokerFill(
            order_id=str(uuid.uuid4()),
            symbol=symbol,
            side=order.side,
            quantity=order.quantity,
            price=fill_price,
            commission=Decimal("0.00"),
            slippage=Decimal("0.00"),
            timestamp=datetime.now(timezone.utc),
            broker_order_id=str(result.order),
        )

    def _place_order_sim(self, order: BrokerOrder) -> BrokerFill:
        slippage = Decimal(
            str(round(random.uniform(0, 0.0002), 6))
        )
        if order.order_type == OrderType.MARKET:
            base_price = self._sim_current_price(order.symbol)
        else:
            base_price = order.price or Decimal("1.100000")

        if order.side == OrderSide.BUY:
            fill_price = base_price + slippage
        else:
            fill_price = base_price - slippage

        ticket = self._next_ticket
        self._next_ticket += 1

        # Pending orders go to _sim_pending, not _sim_positions
        if order.order_type in (OrderType.LIMIT, OrderType.STOP, OrderType.STOP_LIMIT):
            self._sim_pending[ticket] = {
                'symbol': order.symbol,
                'type': f'{order.side.value}_{order.order_type.value}',
                'volume': float(order.quantity),
                'price': float(fill_price),
                'sl': float(order.stop_loss) if order.stop_loss else None,
                'tp': float(order.take_profit) if order.take_profit else None,
                'magic': order.magic_number,
                'comment': order.comment,
            }
            return BrokerFill(
                order_id=str(uuid.uuid4()),
                symbol=order.symbol,
                side=order.side,
                quantity=order.quantity,
                price=fill_price,
                commission=Decimal("0.00"),
                slippage=slippage,
                timestamp=datetime.now(timezone.utc),
                broker_order_id=str(ticket),
            )

        position = BrokerPosition(
            ticket=ticket,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            open_price=fill_price,
            current_price=fill_price,
            unrealized_pnl=Decimal("0.00"),
            swap=Decimal("0.00"),
            commission=Decimal("0.00"),
            open_time=datetime.now(timezone.utc),
            stop_loss=order.stop_loss,
            take_profit=order.take_profit,
            magic_number=order.magic_number,
            comment=order.comment,
        )
        self._sim_positions[ticket] = position

        margin = (
            fill_price * order.quantity / SIMULATED_LEVERAGE
        ).quantize(Decimal("0.01"))
        self._sim_margin += margin
        self._sim_free_margin -= margin

        return BrokerFill(
            order_id=str(uuid.uuid4()),
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            price=fill_price,
            commission=Decimal("0.00"),
            slippage=slippage,
            timestamp=datetime.now(timezone.utc),
            broker_order_id=str(ticket),
        )

    # ------------------------------------------------------------------
    # Position management
    # ------------------------------------------------------------------

    def modify_position(
        self,
        ticket: int,
        stop_loss: Optional[Decimal] = None,
        take_profit: Optional[Decimal] = None,
    ) -> bool:
        if MT5_AVAILABLE and self._connected:
            req = {
                "action": mt5.TRADE_ACTION_SLTP,
                "position": ticket,
            }
            if stop_loss is not None:
                req["sl"] = float(stop_loss)
            if take_profit is not None:
                req["tp"] = float(take_profit)
            result = mt5.order_send(req)
            if result is None:
                return False
            return result.retcode == mt5.TRADE_RETCODE_DONE

        pos = self._sim_positions.get(ticket)
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
        if MT5_AVAILABLE and self._connected:
            return self._close_position_real(ticket, quantity)
        return self._close_position_sim(ticket, quantity)

    def _close_position_real(
        self, ticket: int, quantity: Optional[Decimal]
    ) -> BrokerFill:
        pos_info = mt5.positions_get(ticket=ticket)
        if pos_info is None or len(pos_info) == 0:
            raise RuntimeError(f"Position {ticket} not found")
        pos = pos_info[0]
        close_volume = float(quantity) if quantity else pos.volume
        close_type = (
            mt5.ORDER_TYPE_SELL
            if pos.type == mt5.ORDER_TYPE_BUY
            else mt5.ORDER_TYPE_BUY
        )
        tick = mt5.symbol_info_tick(pos.symbol)
        if tick is None:
            raise RuntimeError(f"Cannot get tick for {pos.symbol}")
        price = tick.bid if pos.type == mt5.ORDER_TYPE_BUY else tick.ask

        req = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": pos.symbol,
            "volume": close_volume,
            "type": close_type,
            "position": ticket,
            "price": price,
            "deviation": 20,
            "comment": "dutchkem close",
        }
        result = mt5.order_send(req)
        if result is None:
            raise RuntimeError("mt5.order_send returned None for close")
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            raise RuntimeError(
                f"MT5 close failed: {result.comment} "
                f"(code={result.retcode})"
            )

        return BrokerFill(
            order_id=str(uuid.uuid4()),
            symbol=pos.symbol,
            side=(
                OrderSide.SELL
                if pos.type == mt5.ORDER_TYPE_BUY
                else OrderSide.BUY
            ),
            quantity=Decimal(str(close_volume)),
            price=Decimal(str(result.price)),
            commission=Decimal("0.00"),
            slippage=Decimal("0.00"),
            timestamp=datetime.now(timezone.utc),
            broker_order_id=str(result.order),
        )

    def _close_position_sim(
        self, ticket: int, quantity: Optional[Decimal]
    ) -> BrokerFill:
        pos = self._sim_positions.get(ticket)
        if pos is None:
            raise RuntimeError(f"Position {ticket} not found")

        close_qty = quantity or pos.quantity
        close_side = (
            OrderSide.SELL if pos.side == OrderSide.BUY else OrderSide.BUY
        )
        slippage = Decimal(
            str(round(random.uniform(0, 0.0002), 6))
        )
        close_price = pos.current_price + slippage

        close_margin = (
            pos.open_price * close_qty / SIMULATED_LEVERAGE
        ).quantize(Decimal("0.01"))
        self._sim_margin -= close_margin
        self._sim_free_margin += close_margin

        if close_qty >= pos.quantity:
            del self._sim_positions[ticket]
        else:
            pos.quantity -= close_qty

        return BrokerFill(
            order_id=str(uuid.uuid4()),
            symbol=pos.symbol,
            side=close_side,
            quantity=close_qty,
            price=close_price,
            commission=Decimal("0.00"),
            slippage=slippage,
            timestamp=datetime.now(timezone.utc),
            broker_order_id=str(ticket),
        )

    # ------------------------------------------------------------------
    # Pending order management (for Gold Hedge EA)
    # ------------------------------------------------------------------

    def cancel_pending_order(self, ticket: int) -> bool:
        """Cancel a pending order by ticket."""
        if MT5_AVAILABLE and self._connected:
            req = {
                "action": mt5.TRADE_ACTION_REMOVE,
                "order": ticket,
            }
            result = mt5.order_send(req)
            if result is None:
                return False
            return result.retcode == mt5.TRADE_RETCODE_DONE

        # Sim mode: just remove from pending dict
        if ticket in self._sim_pending:
            del self._sim_pending[ticket]
            return True
        return False

    def modify_pending_order(
        self,
        ticket: int,
        price: Optional[Decimal] = None,
        stop_loss: Optional[Decimal] = None,
        take_profit: Optional[Decimal] = None,
    ) -> bool:
        """Modify price, SL, or TP of a pending order."""
        if MT5_AVAILABLE and self._connected:
            req = {
                "action": mt5.TRADE_ACTION_SLTP,
                "order": ticket,
            }
            if price is not None:
                req["price"] = float(price)
            if stop_loss is not None:
                req["sl"] = float(stop_loss)
            if take_profit is not None:
                req["tp"] = float(take_profit)
            result = mt5.order_send(req)
            if result is None:
                return False
            return result.retcode == mt5.TRADE_RETCODE_DONE

        # Sim mode
        order = self._sim_pending.get(ticket)
        if order is None:
            return False
        if price is not None:
            order['price'] = price
        if stop_loss is not None:
            order['sl'] = stop_loss
        if take_profit is not None:
            order['tp'] = take_profit
        return True

    def get_pending_orders(self, symbol: str = None, magic: int = None) -> List[Dict]:
        """Get all pending orders, optionally filtered by symbol/magic."""
        if MT5_AVAILABLE and self._connected:
            orders = mt5.orders_get()
            if orders is None:
                return []
            result = []
            for o in orders:
                if symbol and o.symbol != symbol:
                    continue
                if magic and o.magic != magic:
                    continue
                result.append({
                    'ticket': o.ticket,
                    'symbol': o.symbol,
                    'type': o.type,
                    'volume': o.volume_current,
                    'price': o.price_open,
                    'sl': o.sl,
                    'tp': o.tp,
                    'magic': o.magic,
                    'comment': o.comment,
                    'time_setup': o.time_setup,
                })
            return result

        # Sim mode: return from pending dict
        result = []
        for ticket, order in self._sim_pending.items():
            if symbol and order.get('symbol') != symbol:
                continue
            if magic and order.get('magic') != magic:
                continue
            order['ticket'] = ticket
            result.append(order)
        return result

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_positions(self) -> List[BrokerPosition]:
        if MT5_AVAILABLE and self._connected:
            positions = mt5.positions_get()
            if positions is None:
                return []
            return [
                BrokerPosition(
                    ticket=p.ticket,
                    symbol=p.symbol,
                    side=(
                        OrderSide.BUY
                        if p.type == mt5.ORDER_TYPE_BUY
                        else OrderSide.SELL
                    ),
                    quantity=Decimal(str(p.volume)),
                    open_price=Decimal(str(p.price_open)),
                    current_price=Decimal(str(p.price_current)),
                    unrealized_pnl=Decimal(str(p.profit)),
                    swap=Decimal(str(p.swap)),
                    commission=Decimal(str(p.commission)),
                    open_time=datetime.fromtimestamp(
                        p.time, tz=timezone.utc
                    ),
                    stop_loss=(
                        Decimal(str(p.sl)) if p.sl > 0 else None
                    ),
                    take_profit=(
                        Decimal(str(p.tp)) if p.tp > 0 else None
                    ),
                    magic_number=p.magic,
                    comment=p.comment,
                )
                for p in positions
            ]
        return list(self._sim_positions.values())

    def get_position(self, ticket: int) -> Optional[BrokerPosition]:
        if MT5_AVAILABLE and self._connected:
            positions = mt5.positions_get(ticket=ticket)
            if not positions:
                return None
            p = positions[0]
            return BrokerPosition(
                ticket=p.ticket,
                symbol=p.symbol,
                side=(
                    OrderSide.BUY
                    if p.type == mt5.ORDER_TYPE_BUY
                    else OrderSide.SELL
                ),
                quantity=Decimal(str(p.volume)),
                open_price=Decimal(str(p.price_open)),
                current_price=Decimal(str(p.price_current)),
                unrealized_pnl=Decimal(str(p.profit)),
                swap=Decimal(str(p.swap)),
                commission=Decimal(str(p.commission)),
                open_time=datetime.fromtimestamp(
                    p.time, tz=timezone.utc
                ),
                stop_loss=(
                    Decimal(str(p.sl)) if p.sl > 0 else None
                ),
                take_profit=(
                    Decimal(str(p.tp)) if p.tp > 0 else None
                ),
                magic_number=p.magic,
                comment=p.comment,
            )
        return self._sim_positions.get(ticket)

    def get_tick(self, symbol: str) -> Dict[str, Any]:
        if MT5_AVAILABLE and self._connected:
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                raise RuntimeError(f"Cannot get tick for {symbol}")
            return {
                "bid": Decimal(str(tick.bid)),
                "ask": Decimal(str(tick.ask)),
                "spread": Decimal(str(tick.ask - tick.bid)),
                "last": Decimal(str(tick.last)),
                "volume": Decimal(str(tick.volume)),
                "timestamp": datetime.fromtimestamp(
                    tick.time, tz=timezone.utc
                ),
            }
        base = self._sim_current_price(symbol)
        spread = Decimal("0.000150")
        return {
            "bid": base,
            "ask": base + spread,
            "spread": spread,
            "last": base,
            "volume": Decimal("0.00"),
            "timestamp": datetime.now(timezone.utc),
        }

    def get_symbol_info(self, symbol: str) -> Dict[str, Any]:
        if MT5_AVAILABLE and self._connected:
            info = mt5.symbol_info(symbol)
            if info is None:
                raise RuntimeError(f"Cannot get info for {symbol}")
            return {
                "symbol": symbol,
                "digits": info.digits,
                "point": Decimal(str(info.point)),
                "spread": info.spread,
                "volume_min": Decimal(str(info.volume_min)),
                "volume_max": Decimal(str(info.volume_max)),
                "volume_step": Decimal(str(info.volume_step)),
                "trade_contract_size": Decimal(
                    str(info.trade_contract_size)
                ),
                "trade_mode": info.trade_mode,
                "margin_initial": Decimal(str(info.margin_initial)),
                "margin_maintenance": Decimal(
                    str(info.margin_maintenance)
                ),
            }
        return {
            "symbol": symbol,
            "digits": 5,
            "point": Decimal("0.00001"),
            "spread": 15,
            "volume_min": Decimal("0.01"),
            "volume_max": Decimal("100.00"),
            "volume_step": Decimal("0.01"),
            "trade_contract_size": Decimal("100000"),
            "trade_mode": 0,
            "margin_initial": Decimal("0.00"),
            "margin_maintenance": Decimal("0.00"),
        }

    # ------------------------------------------------------------------
    # Simulation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _sim_current_price(symbol: str) -> Decimal:
        """Produce a plausible base price for the symbol in simulation."""
        base_map = {
            "EURUSD": Decimal("1.08500"),
            "GBPUSD": Decimal("1.26500"),
            "USDJPY": Decimal("149.50000"),
            "AUDUSD": Decimal("0.65200"),
            "USDCAD": Decimal("1.36400"),
            "USDCHF": Decimal("0.87800"),
            "NZDUSD": Decimal("0.59800"),
            "XAUUSD": Decimal("2350.00"),
            "BTCUSD": Decimal("64000.00"),
            "US30": Decimal("39500.00"),
        }
        upper = symbol.upper().replace("/", "").replace(".", "")
        return base_map.get(upper, Decimal("1.10000"))
