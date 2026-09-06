from __future__ import annotations

import os
import time
from datetime import datetime, timedelta
from typing import Any, Callable

import httpx

from data.models import Candle, Quote, Tick, Timeframe
from data.providers import BaseDataProvider


_FOREX_PAIRS = {
    "EURUSD",
    "GBPUSD",
    "USDJPY",
    "USDCHF",
    "AUDUSD",
    "USDCAD",
    "NZDUSD",
    "EURGBP",
    "EURJPY",
    "GBPJPY",
    "EURAUD",
    "EURCAD",
    "EURCHF",
    "EURNZD",
    "GBPAUD",
    "GBPCAD",
    "GBPCHF",
    "GBPNZD",
    "AUDCAD",
    "AUDCHF",
    "AUDJPY",
    "AUDNZD",
    "CADJPY",
    "CADCHF",
    "CHFJPY",
    "NZDJPY",
    "NZDCAD",
    "NZDCHF",
}

_TIMEFRAME_MAP: dict[Timeframe, tuple[str, int]] = {
    Timeframe.ONE_MINUTE: ("minute", 1),
    Timeframe.FIVE_MINUTES: ("minute", 5),
    Timeframe.FIFTEEN_MINUTES: ("minute", 15),
    Timeframe.ONE_HOUR: ("hour", 1),
    Timeframe.FOUR_HOURS: ("hour", 4),
    Timeframe.ONE_DAY: ("day", 1),
}

BASE_URL = "https://api.polygon.io"


class PolygonProvider(BaseDataProvider):
    """Polygon.io REST data provider for forex + US equities."""

    name: str = "polygon"

    def __init__(
        self,
        api_key: str | None = None,
        rate_limit_per_min: int = 5,
        timeout: float = 30.0,
    ) -> None:
        self._api_key = api_key or os.environ.get("POLYGON_API_KEY", "")
        if not self._api_key:
            raise ValueError(
                "POLYGON_API_KEY environment variable or api_key parameter required"
            )
        self._client = httpx.AsyncClient(
            base_url=BASE_URL,
            params={"apiKey": self._api_key},
            timeout=timeout,
        )
        self._rate_limit_per_min = rate_limit_per_min
        self._rate_remaining = rate_limit_per_min
        self._rate_limit_reset = time.monotonic() + 60.0
        self._ws_connected = False

    # ── Rate limiting ───────────────────────────────────────────

    def _consume_rate_limit(self) -> None:
        self._reset_if_window_expired()
        if self._rate_remaining > 0:
            self._rate_remaining -= 1

    def _is_rate_limited(self) -> bool:
        self._reset_if_window_expired()
        return self._rate_remaining <= 0

    def _reset_if_window_expired(self) -> None:
        now = time.monotonic()
        if now >= self._rate_limit_reset:
            self._rate_remaining = self._rate_limit_per_min
            self._rate_limit_reset = now + 60.0

    # ── Symbol conversion ──────────────────────────────────────

    def _convert_symbol(self, symbol: str) -> str:
        clean = symbol.replace("/", "").upper()
        if clean.startswith("C:"):
            return clean
        if clean in _FOREX_PAIRS:
            return f"C:{clean}"
        return clean

    # ── Timeframe mapping ──────────────────────────────────────

    def _timeframe_to_polygon(self, tf: Timeframe) -> str:
        mapping = _TIMEFRAME_MAP.get(tf)
        return mapping[0] if mapping else "day"

    def _timeframe_multiplier(self, tf: Timeframe) -> int:
        mapping = _TIMEFRAME_MAP.get(tf)
        return mapping[1] if mapping else 1

    # ── REST API methods ───────────────────────────────────────

    async def _request(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if self._is_rate_limited():
            wait = self._rate_limit_reset - time.monotonic()
            if wait > 0:
                import asyncio
                await asyncio.sleep(wait)
        self._consume_rate_limit()
        resp = await self._client.get(path, params=params)
        resp.raise_for_status()
        return resp.json()

    async def get_candles(
        self, symbol: str, timeframe: Timeframe, limit: int = 100
    ) -> list[Candle]:
        ticker = self._convert_symbol(symbol)
        timespan = self._timeframe_to_polygon(timeframe)
        multiplier = self._timeframe_multiplier(timeframe)

        now_ms = int(time.time() * 1000)
        range_ms = limit * multiplier * _timespan_to_ms(timespan)
        from_ms = now_ms - range_ms

        path = f"/v2/aggs/ticker/{ticker}/range/{multiplier}/{timespan}/{from_ms}/{now_ms}"
        data = await self._request(path, params={"limit": limit, "sort": "desc"})

        results = data.get("results", [])
        return [
            Candle.from_polygon(r, symbol, timeframe)
            for r in results
        ]

    async def get_latest_price(self, symbol: str) -> float:
        ticker = self._convert_symbol(symbol)
        data = await self._request(f"/v3/snapshot/locale/us/markets/stocks/tickers/{ticker}")
        results = data.get("ticker", {}).get("day", {})
        return float(results.get("c", 0.0))

    async def get_quote(self, symbol: str) -> Quote:
        ticker = self._convert_symbol(symbol)
        data = await self._request(f"/v3/quote/{ticker}")
        last_quote = data.get("lastQuote", {})
        return Quote.from_polygon(last_quote, symbol)

    async def get_ticks(self, symbol: str, limit: int = 100) -> list[Tick]:
        ticker = self._convert_symbol(symbol)
        data = await self._request(
            f"/v3/trades/{ticker}",
            params={"limit": limit, "sort": "desc"},
        )
        results = data.get("results", [])
        return [Tick.from_polygon(r) for r in results]

    # ── WebSocket (stub — real implementation deferred) ─────────

    async def connect_websocket(
        self, symbols: list[str], on_tick: Callable[[Tick], Any] | None = None
    ) -> None:
        self._ws_connected = True

    async def disconnect_websocket(self) -> None:
        self._ws_connected = False


def _timespan_to_ms(timespan: str) -> int:
    return {
        "minute": 60_000,
        "hour": 3_600_000,
        "day": 86_400_000,
    }.get(timespan, 86_400_000)
