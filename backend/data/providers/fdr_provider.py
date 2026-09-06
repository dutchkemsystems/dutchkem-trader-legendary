from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any, Callable

try:
    import FinanceDataReader as fdr
    import pandas as pd
except ImportError:
    fdr = None  # type: ignore[assignment]
    pd = None  # type: ignore[assignment]

from data.models import Candle, Quote, Tick, Timeframe
from data.providers import BaseDataProvider


TIMEFRAME_DAYS: dict[Timeframe, int] = {
    Timeframe.ONE_DAY: 1,
    Timeframe.FOUR_HOURS: 1,
    Timeframe.ONE_HOUR: 1,
    Timeframe.FIFTEEN_MINUTES: 1,
    Timeframe.FIVE_MINUTES: 1,
    Timeframe.ONE_MINUTE: 1,
}


class FinanceDataReaderProvider(BaseDataProvider):
    """FinanceDataReader provider — unlimited historical data, REST-only.

    Backup provider #3. Used as a fallback when primary providers
    are rate-limited or unavailable. Supports daily OHLCV data only.
    """

    name: str = "financedatareader"

    def _calc_start(self, limit: int, timeframe: Timeframe) -> str:
        days_per_bar = TIMEFRAME_DAYS.get(timeframe, 1)
        total_days = limit * days_per_bar + 30
        start = datetime.utcnow() - timedelta(days=total_days)
        return start.strftime("%Y-%m-%d")

    def _df_to_candles(
        self, df: pd.DataFrame, symbol: str, timeframe: Timeframe, limit: int
    ) -> list[Candle]:
        if df.empty:
            return []
        df = df.tail(limit)
        candles: list[Candle] = []
        for ts, row in df.iterrows():
            candles.append(
                Candle(
                    symbol=symbol,
                    timeframe=timeframe,
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    volume=int(row["Volume"]),
                    timestamp=ts.to_pydatetime()
                    if hasattr(ts, "to_pydatetime")
                    else datetime.utcnow(),
                )
            )
        return candles

    async def get_candles(
        self, symbol: str, timeframe: Timeframe, limit: int = 100
    ) -> list[Candle]:
        start = self._calc_start(limit, timeframe)
        end = datetime.utcnow().strftime("%Y-%m-%d")
        df = await asyncio.to_thread(fdr.DataReader, symbol, start, end)
        return self._df_to_candles(df, symbol, timeframe, limit)

    async def get_latest_price(self, symbol: str) -> float:
        start = (datetime.utcnow() - timedelta(days=10)).strftime("%Y-%m-%d")
        end = datetime.utcnow().strftime("%Y-%m-%d")
        df = await asyncio.to_thread(fdr.DataReader, symbol, start, end)
        if df.empty:
            raise ValueError(f"No data available for {symbol}")
        return float(df["Close"].iloc[-1])

    async def get_quote(self, symbol: str) -> Quote:
        start = (datetime.utcnow() - timedelta(days=10)).strftime("%Y-%m-%d")
        end = datetime.utcnow().strftime("%Y-%m-%d")
        df = await asyncio.to_thread(fdr.DataReader, symbol, start, end)
        if df.empty:
            raise ValueError(f"No data available for {symbol}")
        last = df.iloc[-1]
        close = float(last["Close"])
        return Quote(
            symbol=symbol,
            bid=close,
            ask=close,
            bid_size=0,
            ask_size=0,
            timestamp=datetime.utcnow(),
        )

    async def get_ticks(self, symbol: str, limit: int = 100) -> list[Tick]:
        return []

    async def connect_websocket(
        self, symbols: list[str], on_tick: Callable[[Tick], Any] | None = None
    ) -> None:
        pass

    async def disconnect_websocket(self) -> None:
        pass
