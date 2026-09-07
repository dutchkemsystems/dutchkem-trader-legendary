"""Tests for SimulatedBroker — in-memory broker for backtesting."""
from decimal import Decimal
from datetime import datetime, timezone

import pytest

from execution.broker import (
    BaseBroker,
    BrokerFill,
    BrokerOrder,
    BrokerPosition,
    OrderSide,
    OrderStatus,
    OrderType,
)


# ---------------------------------------------------------------------------
# FIXTURES
# ---------------------------------------------------------------------------

@pytest.fixture
def broker():
    """Fresh SimulatedBroker instance, connected with default account."""
    from execution.simulated_broker import SimulatedBroker

    b = SimulatedBroker()
    b.connect("SIM-001", "", "Backtest")
    return b


@pytest.fixture
def broker_disconnected():
    """Fresh SimulatedBroker instance, NOT connected."""
    from execution.simulated_broker import SimulatedBroker
    return SimulatedBroker()


# ---------------------------------------------------------------------------
# 1. BaseBroker contract
# ---------------------------------------------------------------------------

class TestIsBaseBroker:
    def test_implements_base_broker(self, broker):
        assert isinstance(broker, BaseBroker)

    def test_all_abstract_methods_implemented(self, broker):
        """Every abstract method on BaseBroker must be callable."""
        for name in (
            "connect",
            "disconnect",
            "is_connected",
            "get_account_info",
            "place_order",
            "modify_position",
            "close_position",
            "get_positions",
            "get_position",
            "get_tick",
            "get_symbol_info",
        ):
            assert callable(getattr(broker, name)), f"{name} not implemented"


# ---------------------------------------------------------------------------
# 2. Connection lifecycle
# ---------------------------------------------------------------------------

class TestConnection:
    def test_connect_sets_connected(self, broker_disconnected):
        result = broker_disconnected.connect("SIM-001", "", "Backtest")
        assert result is True
        assert broker_disconnected.is_connected() is True

    def test_disconnect_clears_state(self, broker):
        broker.disconnect()
        assert broker.is_connected() is False

    def test_connect_stores_credentials(self, broker):
        info = broker.get_account_info()
        assert info.account_number == "SIM-001"


# ---------------------------------------------------------------------------
# 3. Account info
# ---------------------------------------------------------------------------

class TestAccountInfo:
    def test_default_balance(self, broker):
        info = broker.get_account_info()
        assert info.balance == Decimal("10000.00")
        assert info.equity == Decimal("10000.00")
        assert info.leverage == 100
        assert info.currency == "USD"
        assert info.account_type == "STANDARD"

    def test_cent_account_type(self):
        from execution.simulated_broker import SimulatedBroker

        b = SimulatedBroker(initial_balance=Decimal("500.00"))
        b.connect("SIM-002", "", "Backtest")
        info = b.get_account_info()
        assert info.account_type == "CENT"

    def test_free_margin_after_opening_position(self, broker):
        """Opening a BUY order should reserve margin and reduce free_margin."""
        order = BrokerOrder(
            symbol="EURUSD",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("0.10"),
            stop_loss=Decimal("1.08000"),
            take_profit=Decimal("1.09000"),
        )
        broker.place_order(order)

        info = broker.get_account_info()
        assert info.margin > Decimal("0")
        assert info.free_margin < Decimal("10000.00")


# ---------------------------------------------------------------------------
# 4. Place market order
# ---------------------------------------------------------------------------

class TestPlaceMarketOrder:
    def test_buy_market_creates_position(self, broker):
        order = BrokerOrder(
            symbol="EURUSD",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("0.10"),
            stop_loss=Decimal("1.08000"),
            take_profit=Decimal("1.09000"),
        )
        fill = broker.place_order(order)

        assert isinstance(fill, BrokerFill)
        assert fill.symbol == "EURUSD"
        assert fill.side == OrderSide.BUY
        assert fill.quantity == Decimal("0.10")
        assert fill.price > Decimal("0")

        positions = broker.get_positions()
        assert len(positions) == 1
        assert positions[0].symbol == "EURUSD"
        assert positions[0].side == OrderSide.BUY

    def test_sell_market_creates_position(self, broker):
        order = BrokerOrder(
            symbol="GBPUSD",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=Decimal("0.05"),
            stop_loss=Decimal("1.27000"),
            take_profit=Decimal("1.26000"),
        )
        fill = broker.place_order(order)

        assert fill.side == OrderSide.SELL
        positions = broker.get_positions()
        assert len(positions) == 1
        assert positions[0].side == OrderSide.SELL

    def test_limit_order_accepted(self, broker):
        order = BrokerOrder(
            symbol="EURUSD",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("0.10"),
            price=Decimal("1.07000"),
            stop_loss=Decimal("1.06500"),
            take_profit=Decimal("1.08000"),
        )
        fill = broker.place_order(order)
        assert fill.price == Decimal("1.07000")

    def test_stop_order_accepted(self, broker):
        order = BrokerOrder(
            symbol="EURUSD",
            side=OrderSide.BUY,
            order_type=OrderType.STOP,
            quantity=Decimal("0.10"),
            price=Decimal("1.09000"),
            stop_loss=Decimal("1.08500"),
            take_profit=Decimal("1.10000"),
        )
        fill = broker.place_order(order)
        assert fill.price == Decimal("1.09000")

    def test_multiple_orders_independent(self, broker):
        o1 = BrokerOrder(
            symbol="EURUSD",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("0.10"),
            stop_loss=Decimal("1.08000"),
            take_profit=Decimal("1.09000"),
        )
        o2 = BrokerOrder(
            symbol="GBPUSD",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=Decimal("0.05"),
            stop_loss=Decimal("1.27000"),
            take_profit=Decimal("1.25000"),
        )
        broker.place_order(o1)
        broker.place_order(o2)

        positions = broker.get_positions()
        assert len(positions) == 2
        symbols = {p.symbol for p in positions}
        assert symbols == {"EURUSD", "GBPUSD"}


# ---------------------------------------------------------------------------
# 5. Position management
# ---------------------------------------------------------------------------

class TestPositionManagement:
    def test_get_positions_empty(self, broker):
        assert broker.get_positions() == []

    def test_get_position_by_ticket(self, broker):
        order = BrokerOrder(
            symbol="EURUSD",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("0.10"),
            stop_loss=Decimal("1.08000"),
            take_profit=Decimal("1.09000"),
        )
        fill = broker.place_order(order)

        pos = broker.get_position(int(fill.broker_order_id))
        assert pos is not None
        assert pos.symbol == "EURUSD"

    def test_get_position_nonexistent(self, broker):
        assert broker.get_position(999999) is None

    def test_position_tracks_pnl(self, broker):
        order = BrokerOrder(
            symbol="EURUSD",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("0.10"),
            stop_loss=Decimal("1.08000"),
            take_profit=Decimal("1.09000"),
        )
        fill = broker.place_order(order)

        # Simulate price movement
        broker._update_tick("EURUSD", Decimal("1.09000"))

        pos = broker.get_position(int(fill.broker_order_id))
        assert pos is not None
        assert pos.unrealized_pnl > Decimal("0")


# ---------------------------------------------------------------------------
# 6. Modify position (SL/TP)
# ---------------------------------------------------------------------------

class TestModifyPosition:
    def test_modify_stop_loss(self, broker):
        order = BrokerOrder(
            symbol="EURUSD",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("0.10"),
            stop_loss=Decimal("1.08000"),
            take_profit=Decimal("1.09000"),
        )
        fill = broker.place_order(order)
        ticket = int(fill.broker_order_id)

        result = broker.modify_position(ticket, stop_loss=Decimal("1.08200"))
        assert result is True

        pos = broker.get_position(ticket)
        assert pos.stop_loss == Decimal("1.08200")

    def test_modify_take_profit(self, broker):
        order = BrokerOrder(
            symbol="EURUSD",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("0.10"),
            stop_loss=Decimal("1.08000"),
            take_profit=Decimal("1.09000"),
        )
        fill = broker.place_order(order)
        ticket = int(fill.broker_order_id)

        result = broker.modify_position(ticket, take_profit=Decimal("1.09500"))
        assert result is True

        pos = broker.get_position(ticket)
        assert pos.take_profit == Decimal("1.09500")

    def test_modify_nonexistent_returns_false(self, broker):
        result = broker.modify_position(999999, stop_loss=Decimal("1.08000"))
        assert result is False


# ---------------------------------------------------------------------------
# 7. Close position
# ---------------------------------------------------------------------------

class TestClosePosition:
    def test_close_full_position(self, broker):
        order = BrokerOrder(
            symbol="EURUSD",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("0.10"),
            stop_loss=Decimal("1.08000"),
            take_profit=Decimal("1.09000"),
        )
        fill = broker.place_order(order)
        ticket = int(fill.broker_order_id)

        close_fill = broker.close_position(ticket)

        assert isinstance(close_fill, BrokerFill)
        assert close_fill.side == OrderSide.SELL  # opposite of BUY
        assert close_fill.quantity == Decimal("0.10")

        assert broker.get_positions() == []
        assert broker.get_position(ticket) is None

    def test_close_partial_position(self, broker):
        order = BrokerOrder(
            symbol="EURUSD",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("0.10"),
            stop_loss=Decimal("1.08000"),
            take_profit=Decimal("1.09000"),
        )
        fill = broker.place_order(order)
        ticket = int(fill.broker_order_id)

        close_fill = broker.close_position(ticket, quantity=Decimal("0.05"))

        assert close_fill.quantity == Decimal("0.05")

        pos = broker.get_position(ticket)
        assert pos is not None
        assert pos.quantity == Decimal("0.05")

    def test_close_releases_margin(self, broker):
        order = BrokerOrder(
            symbol="EURUSD",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("0.10"),
            stop_loss=Decimal("1.08000"),
            take_profit=Decimal("1.09000"),
        )
        broker.place_order(order)

        info_before = broker.get_account_info()
        margin_before = info_before.margin

        ticket = int(broker.get_positions()[0].ticket)
        broker.close_position(ticket)

        info_after = broker.get_account_info()
        assert info_after.margin < margin_before

    def test_close_nonexistent_raises(self, broker):
        with pytest.raises(RuntimeError, match="not found"):
            broker.close_position(999999)


# ---------------------------------------------------------------------------
# 8. Tick / price feed
# ---------------------------------------------------------------------------

class TestTickFeed:
    def test_get_tick_returns_bid_ask(self, broker):
        tick = broker.get_tick("EURUSD")
        assert "bid" in tick
        assert "ask" in tick
        assert "spread" in tick
        assert tick["ask"] >= tick["bid"]

    def test_get_tick_for_unknown_symbol(self, broker):
        tick = broker.get_tick("USDTRY")
        assert tick["bid"] > Decimal("0")

    def test_update_tick_affects_positions(self, broker):
        order = BrokerOrder(
            symbol="EURUSD",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("0.10"),
            stop_loss=Decimal("1.08000"),
            take_profit=Decimal("1.09000"),
        )
        fill = broker.place_order(order)
        ticket = int(fill.broker_order_id)

        broker._update_tick("EURUSD", Decimal("1.09500"))

        pos = broker.get_position(ticket)
        assert pos.current_price == Decimal("1.09500")
        assert pos.unrealized_pnl > Decimal("0")


# ---------------------------------------------------------------------------
# 9. Symbol info
# ---------------------------------------------------------------------------

class TestSymbolInfo:
    def test_get_symbol_info(self, broker):
        info = broker.get_symbol_info("EURUSD")
        assert info["symbol"] == "EURUSD"
        assert info["digits"] == 5
        assert info["point"] == Decimal("0.00001")

    def test_get_symbol_info_unknown(self, broker):
        info = broker.get_symbol_info("USDTRY")
        assert "symbol" in info


# ---------------------------------------------------------------------------
# 10. Balance / equity tracking
# ---------------------------------------------------------------------------

class TestBalanceTracking:
    def test_balance_unchanged_after_open(self, broker):
        order = BrokerOrder(
            symbol="EURUSD",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("0.10"),
            stop_loss=Decimal("1.08000"),
            take_profit=Decimal("1.09000"),
        )
        broker.place_order(order)

        info = broker.get_account_info()
        assert info.balance == Decimal("10000.00")  # balance unchanged

    def test_equity_updates_with_price(self, broker):
        order = BrokerOrder(
            symbol="EURUSD",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("0.10"),
            stop_loss=Decimal("1.08000"),
            take_profit=Decimal("1.09000"),
        )
        broker.place_order(order)

        # Price moves up
        broker._update_tick("EURUSD", Decimal("1.09500"))

        info = broker.get_account_info()
        assert info.equity > info.balance

    def test_close_profit_adds_to_balance(self, broker):
        order = BrokerOrder(
            symbol="EURUSD",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("0.10"),
            stop_loss=Decimal("1.08000"),
            take_profit=Decimal("1.09000"),
        )
        fill = broker.place_order(order)
        ticket = int(fill.broker_order_id)

        # Price moves up
        broker._update_tick("EURUSD", Decimal("1.09500"))

        broker.close_position(ticket)

        info = broker.get_account_info()
        assert info.balance > Decimal("10000.00")
        assert info.equity == info.balance  # no open positions

    def test_close_loss_reduces_balance(self, broker):
        order = BrokerOrder(
            symbol="EURUSD",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("0.10"),
            stop_loss=Decimal("1.08000"),
            take_profit=Decimal("1.09000"),
        )
        fill = broker.place_order(order)
        ticket = int(fill.broker_order_id)

        # Price moves down
        broker._update_tick("EURUSD", Decimal("1.07500"))

        broker.close_position(ticket)

        info = broker.get_account_info()
        assert info.balance < Decimal("10000.00")


# ---------------------------------------------------------------------------
# 11. Trade history
# ---------------------------------------------------------------------------

class TestTradeHistory:
    def test_trade_history_populated(self, broker):
        order = BrokerOrder(
            symbol="EURUSD",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("0.10"),
            stop_loss=Decimal("1.08000"),
            take_profit=Decimal("1.09000"),
        )
        broker.place_order(order)

        history = broker.get_trade_history()
        assert len(history) == 1
        assert history[0].symbol == "EURUSD"
        assert history[0].side == OrderSide.BUY

    def test_trade_history_after_close(self, broker):
        order = BrokerOrder(
            symbol="EURUSD",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("0.10"),
            stop_loss=Decimal("1.08000"),
            take_profit=Decimal("1.09000"),
        )
        fill = broker.place_order(order)
        ticket = int(fill.broker_order_id)
        broker.close_position(ticket)

        history = broker.get_trade_history()
        assert len(history) == 2  # open + close
        assert history[1].side == OrderSide.SELL


# ---------------------------------------------------------------------------
# 12. Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_insufficient_margin(self):
        """Order exceeding available margin should fail."""
        from execution.simulated_broker import SimulatedBroker

        b = SimulatedBroker(initial_balance=Decimal("10.00"))
        b.connect("SIM-001", "", "Backtest")

        order = BrokerOrder(
            symbol="EURUSD",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("1.0"),
            stop_loss=Decimal("1.00000"),
            take_profit=Decimal("1.10000"),
        )
        # 1.0 lot at ~1.085 with 100x leverage → margin ≈ 0.01085, which is < 10
        # Need to fill all available margin first, then try to exceed
        # With $10 balance and 100x leverage, max controlled = $1000
        # 1 lot EURUSD = 1.085 * 1.0 / 100 = 0.01085 margin
        # We need quantity that exceeds 10 / 0.01085 ≈ 921 lots
        big_order = BrokerOrder(
            symbol="EURUSD",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("1000.0"),
            stop_loss=Decimal("1.00000"),
            take_profit=Decimal("1.10000"),
        )
        with pytest.raises(RuntimeError, match="margin"):
            b.place_order(big_order)

    def test_connect_idempotent(self, broker_disconnected):
        broker_disconnected.connect("A", "", "S1")
        broker_disconnected.connect("B", "", "S2")
        info = broker_disconnected.get_account_info()
        assert info.account_number == "B"

    def test_positions_isolation_between_instances(self):
        from execution.simulated_broker import SimulatedBroker

        b1 = SimulatedBroker()
        b1.connect("SIM-1", "", "S")
        b1.place_order(BrokerOrder(
            symbol="EURUSD",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("0.10"),
            stop_loss=Decimal("1.08000"),
            take_profit=Decimal("1.09000"),
        ))

        b2 = SimulatedBroker()
        b2.connect("SIM-2", "", "S")
        assert b2.get_positions() == []

    def test_configurable_initial_balance(self):
        from execution.simulated_broker import SimulatedBroker

        b = SimulatedBroker(initial_balance=Decimal("5000.00"))
        b.connect("SIM-3", "", "S")
        info = b.get_account_info()
        assert info.balance == Decimal("5000.00")

    def test_configurable_commission(self):
        from execution.simulated_broker import SimulatedBroker

        b = SimulatedBroker(commission_per_lot=Decimal("7.00"))
        b.connect("SIM-4", "", "S")
        fill = b.place_order(BrokerOrder(
            symbol="EURUSD",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("0.10"),
            stop_loss=Decimal("1.08000"),
            take_profit=Decimal("1.09000"),
        ))
        assert fill.commission == Decimal("0.70")  # 7.00 * 0.10

    def test_configurable_slippage(self):
        from execution.simulated_broker import SimulatedBroker

        b = SimulatedBroker(max_slippage_pips=Decimal("2"))
        b.connect("SIM-5", "", "S")
        fill = b.place_order(BrokerOrder(
            symbol="EURUSD",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("0.10"),
            stop_loss=Decimal("1.08000"),
            take_profit=Decimal("1.09000"),
        ))
        assert fill.slippage <= Decimal("0.00020")  # 2 pips max
