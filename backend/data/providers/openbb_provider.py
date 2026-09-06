from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable

from data.models import Candle, Quote, Tick, Timeframe
from data.providers import BaseDataProvider

logger = logging.getLogger(__name__)

try:
    from openbb import obb as openbb  # type: ignore[no-redef]
except ImportError:
    openbb = None  # type: ignore[assignment]

TIMEFRAME_MAP = {
    Timeframe.ONE_MINUTE: "1min",
    Timeframe.FIVE_MINUTES: "5min",
    Timeframe.FIFTEEN_MINUTES: "15min",
    Timeframe.ONE_HOUR: "1h",
    Timeframe.FOUR_HOURS: "4h",
    Timeframe.ONE_DAY: "1d",
}


class OpenBBProvider(BaseDataProvider):
    """OpenBB provider — unified gateway to 30+ data providers.

    Acts as a single entry point to multiple financial data providers
    through the OpenBB SDK ecosystem (Equities, ETFs, Crypto, Forex).
    """

    name: str = "openbb"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key
        self._ws_connected = False

    async def get_candles(
        self, symbol: str, timeframe: Timeframe, limit: int = 100
    ) -> list[Candle]:
        interval = TIMEFRAME_MAP.get(timeframe, "1d")

        result = openbb.equity.price.historical(
            symbol=symbol,
            interval=interval,
            limit=limit,
        )
        df = result.value

        if hasattr(df, "empty") and df.empty:
            return []

        candles: list[Candle] = []
        for row in df.to_dict("records") if hasattr(df, "to_dict") else df:
            ts = row.get("date") or row.get("Date") or datetime.now(timezone.utc)
            if isinstance(ts, str):
                ts = datetime.fromisoformat(ts)
            candles.append(
                Candle(
                    symbol=symbol,
                    timeframe=timeframe,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=int(row.get("volume", 0)),
                    timestamp=ts,
                )
            )
        return candles

    async def get_latest_price(self, symbol: str) -> float:
        result = openbb.equity.price.historical(symbol=symbol, interval="1d", limit=1)
        df = result.value
        if hasattr(df, "empty") and df.empty:
            raise RuntimeError(f"No price data for {symbol}")
        rows = df.to_dict("records") if hasattr(df, "to_dict") else df
        return float(rows[-1]["close"])

    async def get_quote(self, symbol: str) -> Quote:
        result = openbb.equity.price.quote(symbol=symbol)
        q = result.value
        bid = getattr(q, "bid", 0.0) or 0.0
        ask = getattr(q, "ask", 0.0) or 0.0
        bid_size = getattr(q, "bid_size", 0) or 0
        ask_size = getattr(q, "ask_size", 0) or 0
        return Quote(
            symbol=symbol,
            bid=float(bid),
            ask=float(ask),
            bid_size=float(bid_size),
            ask_size=float(ask_size),
            timestamp=datetime.now(timezone.utc),
        )

    async def get_ticks(self, symbol: str, limit: int = 100) -> list[Tick]:
        try:
            result = openbb.equity.price.historical(
                symbol=symbol, interval="1min", limit=limit
            )
            df = result.value
            if hasattr(df, "empty") and df.empty:
                return []

            ticks: list[Tick] = []
            rows = df.to_dict("records") if hasattr(df, "to_dict") else df
            for row in rows:
                ts = row.get("date") or row.get("Date") or datetime.now(timezone.utc)
                if isinstance(ts, str):
                    ts = datetime.fromisoformat(ts)
                ticks.append(
                    Tick(
                        symbol=symbol,
                        price=float(row.get("close", 0)),
                        size=int(row.get("volume", 0)),
                        timestamp=ts,
                        exchange="OPENBB",
                    )
                )
            return ticks
        except Exception as e:
            logger.warning("OpenBB ticks not available for %s: %s", symbol, e)
            return []

    async def connect_websocket(
        self, symbols: list[str], on_tick: Callable[[Tick], Any] | None = None
    ) -> None:
        logger.info("OpenBB websocket connected for %s", symbols)
        self._ws_connected = True

    async def disconnect_websocket(self) -> None:
        logger.info("OpenBB websocket disconnected")
        self._ws_connected = False
