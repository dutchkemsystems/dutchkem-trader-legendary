"""Tests for in-memory Portfolio used in backtesting."""
import pytest
from decimal import Decimal
from backtesting.portfolio import Portfolio, PortfolioTrade


class TestPortfolio:
    def test_initial_state(self):
        p = Portfolio(initial_balance=Decimal("10000"))
        assert p.balance == Decimal("10000")
        assert p.equity == Decimal("10000")
        assert p.open_positions == []
        assert p.closed_trades == []

    def test_open_position(self):
        p = Portfolio(initial_balance=Decimal("10000"))
        p.open_position("EURUSD", "BUY", Decimal("0.1"), Decimal("1.0852"))
        assert len(p.open_positions) == 1
        assert p.open_positions[0].symbol == "EURUSD"

    def test_close_position_profit(self):
        p = Portfolio(initial_balance=Decimal("10000"))
        p.open_position("EURUSD", "BUY", Decimal("0.1"), Decimal("1.0852"))
        p.close_position(0, Decimal("1.0952"), Decimal("0"))
        assert len(p.closed_trades) == 1
        assert p.closed_trades[0].pnl > 0
        assert p.balance > Decimal("10000")

    def test_close_position_loss(self):
        p = Portfolio(initial_balance=Decimal("10000"))
        p.open_position("EURUSD", "BUY", Decimal("0.1"), Decimal("1.0852"))
        p.close_position(0, Decimal("1.0752"), Decimal("0"))
        assert p.closed_trades[0].pnl < 0
        assert p.balance < Decimal("10000")

    def test_equity_with_open_positions(self):
        p = Portfolio(initial_balance=Decimal("10000"), contract_size=100000)
        p.open_position("EURUSD", "BUY", Decimal("0.1"), Decimal("1.0852"))
        p.update_prices({"EURUSD": {"bid": Decimal("1.0900"), "high": Decimal("1.0900"), "low": Decimal("1.0850")}})
        assert p.equity > p.balance

    def test_multiple_positions(self):
        p = Portfolio(initial_balance=Decimal("10000"))
        p.open_position("EURUSD", "BUY", Decimal("0.1"), Decimal("1.0852"))
        p.open_position("GBPUSD", "SELL", Decimal("0.05"), Decimal("1.2700"))
        assert len(p.open_positions) == 2

    def test_trade_history(self):
        p = Portfolio(initial_balance=Decimal("10000"))
        p.open_position("EURUSD", "BUY", Decimal("0.1"), Decimal("1.0852"))
        p.close_position(0, Decimal("1.0952"), Decimal("0"))
        assert len(p.closed_trades) == 1
        trade = p.closed_trades[0]
        assert trade.symbol == "EURUSD"
        assert trade.side == "BUY"

    def test_close_sell_position_profit(self):
        p = Portfolio(initial_balance=Decimal("10000"), contract_size=100000)
        p.open_position("EURUSD", "SELL", Decimal("0.1"), Decimal("1.0852"))
        p.close_position(0, Decimal("1.0752"), Decimal("0"))
        assert p.closed_trades[0].pnl > 0
        assert p.balance > Decimal("10000")

    def test_close_sell_position_loss(self):
        p = Portfolio(initial_balance=Decimal("10000"), contract_size=100000)
        p.open_position("EURUSD", "SELL", Decimal("0.1"), Decimal("1.0852"))
        p.close_position(0, Decimal("1.0952"), Decimal("0"))
        assert p.closed_trades[0].pnl < 0
        assert p.balance < Decimal("10000")

    def test_commission_deducted_from_pnl(self):
        p = Portfolio(initial_balance=Decimal("10000"), contract_size=100000)
        p.open_position("EURUSD", "BUY", Decimal("0.1"), Decimal("1.0852"))
        p.close_position(0, Decimal("1.0952"), Decimal("7.00"))
        assert p.closed_trades[0].commission == Decimal("7.00")
        expected_pnl = (Decimal("1.0952") - Decimal("1.0852")) * Decimal("0.1") * 100000 - Decimal("7.00")
        assert p.closed_trades[0].pnl == expected_pnl

    def test_equity_unaffected_by_closed_trades(self):
        p = Portfolio(initial_balance=Decimal("10000"), contract_size=100000)
        p.open_position("EURUSD", "BUY", Decimal("0.1"), Decimal("1.0852"))
        p.close_position(0, Decimal("1.0952"), Decimal("0"))
        assert p.equity == p.balance  # no open positions

    def test_open_positions_returns_copy(self):
        p = Portfolio(initial_balance=Decimal("10000"))
        p.open_position("EURUSD", "BUY", Decimal("0.1"), Decimal("1.0852"))
        positions = p.open_positions
        positions.clear()
        assert len(p.open_positions) == 1  # original unaffected

    def test_closed_trades_returns_copy(self):
        p = Portfolio(initial_balance=Decimal("10000"))
        p.open_position("EURUSD", "BUY", Decimal("0.1"), Decimal("1.0852"))
        p.close_position(0, Decimal("1.0952"), Decimal("0"))
        trades = p.closed_trades
        trades.clear()
        assert len(p.closed_trades) == 1  # original unaffected


class TestPortfolioSlTp:
    def test_sl_hit_buy_position(self):
        p = Portfolio(initial_balance=Decimal("10000"), contract_size=100000)
        p.open_position("EURUSD", "BUY", Decimal("0.1"), Decimal("1.0852"),
                        stop_loss=Decimal("1.0802"))
        p.update_prices({"EURUSD": {"bid": Decimal("1.0790"), "high": Decimal("1.0850"), "low": Decimal("1.0790")}})
        hits = p.check_sl_tp_hits()
        assert len(hits) == 1
        assert hits[0] == (0, Decimal("1.0802"))

    def test_tp_hit_buy_position(self):
        p = Portfolio(initial_balance=Decimal("10000"), contract_size=100000)
        p.open_position("EURUSD", "BUY", Decimal("0.1"), Decimal("1.0852"),
                        take_profit=Decimal("1.0952"))
        p.update_prices({"EURUSD": {"bid": Decimal("1.0960"), "high": Decimal("1.0960"), "low": Decimal("1.0850")}})
        hits = p.check_sl_tp_hits()
        assert len(hits) == 1
        assert hits[0] == (0, Decimal("1.0952"))

    def test_sl_hit_sell_position(self):
        p = Portfolio(initial_balance=Decimal("10000"), contract_size=100000)
        p.open_position("EURUSD", "SELL", Decimal("0.1"), Decimal("1.0852"),
                        stop_loss=Decimal("1.0902"))
        p.update_prices({"EURUSD": {"bid": Decimal("1.0910"), "high": Decimal("1.0910"), "low": Decimal("1.0850")}})
        hits = p.check_sl_tp_hits()
        assert len(hits) == 1
        assert hits[0] == (0, Decimal("1.0902"))

    def test_tp_hit_sell_position(self):
        p = Portfolio(initial_balance=Decimal("10000"), contract_size=100000)
        p.open_position("EURUSD", "SELL", Decimal("0.1"), Decimal("1.0852"),
                        take_profit=Decimal("1.0752"))
        p.update_prices({"EURUSD": {"bid": Decimal("1.0740"), "high": Decimal("1.0850"), "low": Decimal("1.0740")}})
        hits = p.check_sl_tp_hits()
        assert len(hits) == 1
        assert hits[0] == (0, Decimal("1.0752"))

    def test_no_hits_when_price_in_range(self):
        p = Portfolio(initial_balance=Decimal("10000"), contract_size=100000)
        p.open_position("EURUSD", "BUY", Decimal("0.1"), Decimal("1.0852"),
                        stop_loss=Decimal("1.0802"), take_profit=Decimal("1.0952"))
        p.update_prices({"EURUSD": {"bid": Decimal("1.0870"), "high": Decimal("1.0880"), "low": Decimal("1.0860")}})
        hits = p.check_sl_tp_hits()
        assert len(hits) == 0

    def test_no_hits_without_prices(self):
        p = Portfolio(initial_balance=Decimal("10000"))
        p.open_position("EURUSD", "BUY", Decimal("0.1"), Decimal("1.0852"),
                        stop_loss=Decimal("1.0802"))
        hits = p.check_sl_tp_hits()
        assert len(hits) == 0

    def test_no_sl_tp_returns_empty(self):
        p = Portfolio(initial_balance=Decimal("10000"), contract_size=100000)
        p.open_position("EURUSD", "BUY", Decimal("0.1"), Decimal("1.0852"))
        p.update_prices({"EURUSD": {"bid": Decimal("1.0900"), "high": Decimal("1.0900"), "low": Decimal("1.0800")}})
        hits = p.check_sl_tp_hits()
        assert len(hits) == 0

    def test_multiple_positions_sl_tp(self):
        p = Portfolio(initial_balance=Decimal("10000"), contract_size=100000)
        p.open_position("EURUSD", "BUY", Decimal("0.1"), Decimal("1.0852"),
                        stop_loss=Decimal("1.0802"), take_profit=Decimal("1.0952"))
        p.open_position("GBPUSD", "SELL", Decimal("0.05"), Decimal("1.2700"),
                        stop_loss=Decimal("1.2800"), take_profit=Decimal("1.2600"))
        p.update_prices({
            "EURUSD": {"bid": Decimal("1.0960"), "high": Decimal("1.0960"), "low": Decimal("1.0850")},
            "GBPUSD": {"bid": Decimal("1.2590"), "high": Decimal("1.2710"), "low": Decimal("1.2590")},
        })
        hits = p.check_sl_tp_hits()
        assert len(hits) == 2


class TestPortfolioConfigurable:
    def test_custom_initial_balance(self):
        p = Portfolio(initial_balance=Decimal("5000"))
        assert p.balance == Decimal("5000")
        assert p.equity == Decimal("5000")

    def test_custom_contract_size(self):
        p = Portfolio(initial_balance=Decimal("10000"), contract_size=10000)
        p.open_position("EURUSD", "BUY", Decimal("0.1"), Decimal("1.0852"))
        p.close_position(0, Decimal("1.0952"), Decimal("0"))
        expected_pnl = (Decimal("1.0952") - Decimal("1.0852")) * Decimal("0.1") * 10000
        assert p.closed_trades[0].pnl == expected_pnl
