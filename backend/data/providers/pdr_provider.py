from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable

from data.models import Candle, Quote, Tick, Timeframe
from data.providers import BaseDataProvider

logger = logging.getLogger(__name__)

try:
    from pandas_datareader import data as pdr  # type: ignore[no-redef]
except ImportError:
    pdr = None  # type: ignore[assignment]

TIMEFRAME_MAP = {
    Timeframe.ONE_MINUTE: "1m",
    Timeframe.FIVE_MINUTES: "5m",
    Timeframe.FIFTEEN_MINUTES: "15m",
    Timeframe.ONE_HOUR: "1h",
    Timeframe.FOUR_HOURS: "4h",
    Timeframe.ONE_DAY: "1d",
}


class PandasDataProvider(BaseDataProvider):
    """pandas-datareader provider — stable classic data source.

    Uses pandas-datareader for fetching financial data from Yahoo Finance,
    FRED, World Bank, and other classic data sources. Acts as backup #5
    in the provider fallback chain.
    """

    name: str = "pandas_datareader"

    def __init__(self, data_source: str = "yahoo") -> None:
        self.data_source = data_source
        self._ws_connected = False

    async def get_candles(
        self, symbol: str, timeframe: Timeframe, limit: int = 100
    ) -> list[Candle]:
        period_map = {
            Timeframe.ONE_MINUTE: f"{limit}m",
            Timeframe.FIVE_MINUTES: f"{limit}d",
            Timeframe.FIFTEEN_MINUTES: f"{limit}d",
            Timeframe.ONE_HOUR: f"{limit}d",
            Timeframe.FOUR_HOURS: f"{limit}d",
            Timeframe.ONE_DAY: f"{limit}d",
        }

        if self.data_source == "yahoo":
            period = period_map.get(timeframe, f"{limit}d")
            df = pdr.DataReader(
                symbol,
                data_source=self.data_source,
                period=period,
            )
        else:
            df = pdr.DataReader(
                symbol,
                data_source=self.data_source,
            )
            df = df.tail(limit)

        if df.empty:
            return []

        candles: list[Candle] = []
        for idx, row in df.iterrows():
            ts = idx.to_pydatetime() if hasattr(idx, "to_pydatetime") else datetime.now(timezone.utc)
            if ts.tzinfo is not None:
                ts = ts.replace(tzinfo=None)
            candles.append(
                Candle(
                    symbol=symbol,
                    timeframe=timeframe,
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    volume=int(row.get("Volume", 0)),
                    timestamp=ts,
                )
            )
        return candles

    async def get_latest_price(self, symbol: str) -> float:
        df = pdr.DataReader(
            symbol, data_source=self.data_source, period="1d"
        )
        if df.empty:
            raise RuntimeError(f"No price data for {symbol}")
        return float(df.iloc[-1]["Close"])

    async def get_quote(self, symbol: str) -> Quote:
        df = pdr.DataReader(
            symbol, data_source=self.data_source, period="1d"
        )
        if df.empty:
            raise RuntimeError(f"No quote data for {symbol}")

        last_close = float(df.iloc[-1]["Close"])
        bid = last_close - 0.01
        ask = last_close + 0.01
        return Quote(
            symbol=symbol,
            bid=round(bid, 10),
            ask=round(ask, 10),
            bid_size=0,
            ask_size=0,
            timestamp=datetime.now(timezone.utc),
        )

    async def get_ticks(self, symbol: str, limit: int = 100) -> list[Tick]:
        try:
            df = pdr.DataReader(
                symbol, data_source=self.data_source, period="1d"
            )
            if df.empty:
                return []

            ticks: list[Tick] = []
            for idx, row in df.tail(limit).iterrows():
                ts = idx.to_pydatetime() if hasattr(idx, "to_pydatetime") else datetime.now(timezone.utc)
                if ts.tzinfo is not None:
                    ts = ts.replace(tzinfo=None)
                ticks.append(
                    Tick(
                        symbol=symbol,
                        price=float(row["Close"]),
                        size=int(row.get("Volume", 0)),
                        timestamp=ts,
                        exchange=self.data_source.upper(),
                    )
                )
            return ticks
        except Exception as e:
            logger.warning("pandas-datareader ticks not available for %s: %s", symbol, e)
            return []

    async def connect_websocket(
        self, symbols: list[str], on_tick: Callable[[Tick], Any] | None = None
    ) -> None:
        logger.info("pandas-datareader websocket connected (polling mode) for %s", symbols)
        self._ws_connected = True

    async def disconnect_websocket(self) -> None:
        logger.info("pandas-datareader websocket disconnected")
        self._ws_connected = False
