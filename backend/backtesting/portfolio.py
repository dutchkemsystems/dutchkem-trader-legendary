"""In-memory portfolio for backtesting — no Django ORM."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List, Optional, Tuple


@dataclass
class PortfolioTrade:
    symbol: str
    side: str
    quantity: Decimal
    entry_price: Decimal
    exit_price: Decimal
    pnl: Decimal
    commission: Decimal = Decimal("0")


@dataclass
class _OpenPosition:
    symbol: str
    side: str
    quantity: Decimal
    entry_price: Decimal
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None


class Portfolio:
    def __init__(self, initial_balance: Decimal = Decimal("10000"),
                 contract_size: int = 100000):
        self._initial_balance = initial_balance
        self._balance = initial_balance
        self._contract_size = contract_size
        self._open_positions: List[_OpenPosition] = []
        self._closed_trades: List[PortfolioTrade] = []
        self._current_prices: Dict[str, Dict[str, Decimal]] = {}

    @property
    def balance(self) -> Decimal:
        return self._balance

    @property
    def equity(self) -> Decimal:
        unrealized = sum(self._unrealized_pnl(pos) for pos in self._open_positions)
        return self._balance + unrealized

    @property
    def open_positions(self) -> List[_OpenPosition]:
        return list(self._open_positions)

    @property
    def closed_trades(self) -> List[PortfolioTrade]:
        return list(self._closed_trades)

    def open_position(self, symbol: str, side: str, quantity: Decimal,
                      entry_price: Decimal, stop_loss: Optional[Decimal] = None,
                      take_profit: Optional[Decimal] = None):
        pos = _OpenPosition(symbol, side, quantity, entry_price, stop_loss, take_profit)
        self._open_positions.append(pos)

    def close_position(self, index: int, exit_price: Decimal, commission: Decimal = Decimal("0")):
        pos = self._open_positions.pop(index)
        if pos.side == "BUY":
            pnl = (exit_price - pos.entry_price) * pos.quantity * self._contract_size
        else:
            pnl = (pos.entry_price - exit_price) * pos.quantity * self._contract_size
        pnl -= commission
        self._balance += pnl
        self._closed_trades.append(PortfolioTrade(
            symbol=pos.symbol, side=pos.side, quantity=pos.quantity,
            entry_price=pos.entry_price, exit_price=exit_price,
            pnl=pnl, commission=commission,
        ))

    def update_prices(self, prices: Dict[str, Dict[str, Decimal]]):
        """Update with candle OHLC: prices[symbol] = {"bid": close, "high": h, "low": l}"""
        for symbol, data in prices.items():
            if symbol not in self._current_prices:
                self._current_prices[symbol] = {}
            self._current_prices[symbol].update(data)

    def check_sl_tp_hits(self) -> List[Tuple[int, Decimal]]:
        """Check if any open positions hit SL/TP using candle high/low.

        For BUY positions: check if low <= stop_loss or high >= take_profit
        For SELL positions: check if high >= stop_loss or low <= take_profit
        Returns list of (index, exit_price).
        """
        hits: List[Tuple[int, Decimal]] = []
        for i, pos in enumerate(self._open_positions):
            data = self._current_prices.get(pos.symbol)
            if data is None:
                continue
            high = data.get("high")
            low = data.get("low")
            if high is None or low is None:
                continue

            if pos.side == "BUY":
                if pos.stop_loss and low <= pos.stop_loss:
                    hits.append((i, pos.stop_loss))
                elif pos.take_profit and high >= pos.take_profit:
                    hits.append((i, pos.take_profit))
            else:  # SELL
                if pos.stop_loss and high >= pos.stop_loss:
                    hits.append((i, pos.stop_loss))
                elif pos.take_profit and low <= pos.take_profit:
                    hits.append((i, pos.take_profit))
        return hits

    def _unrealized_pnl(self, pos: _OpenPosition) -> Decimal:
        data = self._current_prices.get(pos.symbol, {})
        price = data.get("bid", pos.entry_price)
        if pos.side == "BUY":
            return (price - pos.entry_price) * pos.quantity * self._contract_size
        else:
            return (pos.entry_price - price) * pos.quantity * self._contract_size
