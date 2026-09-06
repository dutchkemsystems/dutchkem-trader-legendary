from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable

import aiohttp

from data.models import Candle, Quote, Tick, Timeframe
from data.providers import BaseDataProvider

logger = logging.getLogger(__name__)

TIMEFRAME_RESOLUTION: dict[Timeframe, str] = {
    Timeframe.ONE_MINUTE: "1",
    Timeframe.FIVE_MINUTES: "5",
    Timeframe.FIFTEEN_MINUTES: "15",
    Timeframe.ONE_HOUR: "60",
    Timeframe.FOUR_HOURS: "D",
    Timeframe.ONE_DAY: "D",
}

_SECONDS_PER_RESOLUTION: dict[str, int] = {
    "1": 60,
    "5": 300,
    "15": 900,
    "60": 3600,
    "D": 86400,
}


class FinnhubProvider(BaseDataProvider):
    """Finnhub data provider — backup #1, 60 API calls/min free tier.

    Supports: real-time quotes, OHLCV candles, WebSocket trades.
    """

    name: str = "finnhub"

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://finnhub.io/api/v1",
    ) -> None:
        if not api_key:
            raise ValueError("api_key is required for FinnhubProvider")
        self.api_key = api_key
        self.base_url = base_url
        self._max_requests_per_minute: int = 60
        self._request_times: list[float] = []
        self._client: aiohttp.ClientSession | None = None
        self._ws: Any = None
        self._ws_task: asyncio.Task | None = None

    def _timeframe_to_resolution(self, timeframe: Timeframe) -> str:
        return TIMEFRAME_RESOLUTION[timeframe]

    async def _ensure_client(self) -> aiohttp.ClientSession:
        if self._client is None or self._client.closed:
            self._client = aiohttp.ClientSession()
        return self._client

    async def _rate_limit(self) -> None:
        now = time.monotonic()
        self._request_times = [t for t in self._request_times if now - t < 60]
        if len(self._request_times) >= self._max_requests_per_minute:
            wait_time = 60.0 - (now - self._request_times[0])
            if wait_time > 0:
                logger.warning("Finnhub rate limit reached, sleeping %.1fs", wait_time)
                await asyncio.sleep(wait_time)
        self._request_times.append(time.monotonic())

    async def _request(
        self, endpoint: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        await self._rate_limit()
        client = await self._ensure_client()
        req_params = dict(params or {})
        req_params["token"] = self.api_key
        url = f"{self.base_url}/{endpoint}"

        async with client.get(url, params=req_params) as resp:
            if resp.status == 429:
                raise RuntimeError("Finnhub API error: rate limit exceeded (429)")
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"Finnhub API error: {resp.status} - {text}")
            return await resp.json()

    async def get_candles(
        self, symbol: str, timeframe: Timeframe, limit: int = 100
    ) -> list[Candle]:
        resolution = self._timeframe_to_resolution(timeframe)
        now = int(time.time())
        sec_per = _SECONDS_PER_RESOLUTION.get(resolution, 86400)
        from_ts = now - (sec_per * limit * 2)

        data = await self._request(
            "stock/candle",
            {
                "symbol": symbol,
                "resolution": resolution,
                "from": from_ts,
                "to": now,
            },
        )

        if data.get("s") != "ok" or not data.get("t"):
            return []

        candles: list[Candle] = []
        for i in range(len(data["t"])):
            candles.append(
                Candle(
                    symbol=symbol,
                    timeframe=timeframe,
                    open=float(data["o"][i]),
                    high=float(data["h"][i]),
                    low=float(data["l"][i]),
                    close=float(data["c"][i]),
                    volume=int(data["v"][i]),
                    timestamp=datetime.fromtimestamp(data["t"][i], tz=timezone.utc),
                )
            )
        return candles[-limit:]

    async def get_latest_price(self, symbol: str) -> float:
        data = await self._request("quote", {"symbol": symbol})
        return float(data.get("c", 0))

    async def get_quote(self, symbol: str) -> Quote:
        data = await self._request("quote", {"symbol": symbol})
        current_price = float(data.get("c", 0))
        spread = current_price * 0.0002
        return Quote(
            symbol=symbol,
            bid=round(current_price - spread / 2, 6),
            ask=round(current_price + spread / 2, 6),
            bid_size=0,
            ask_size=0,
            timestamp=datetime.now(tz=timezone.utc),
        )

    async def get_ticks(self, symbol: str, limit: int = 100) -> list[Tick]:
        return []

    async def connect_websocket(
        self,
        symbols: list[str],
        on_tick: Callable[[Tick], Any] | None = None,
    ) -> None:
        try:
            import websockets  # noqa: F401
        except ImportError:
            logger.warning("websockets package not installed, WS unavailable")
            return

        ws_url = f"wss://ws.finnhub.io?token={self.api_key}"

        async def _ws_handler() -> None:
            try:
                async with __import__("websockets").connect(ws_url) as ws:
                    self._ws = ws
                    for sym in symbols:
                        await ws.send(
                            json.dumps({"type": "subscribe", "symbol": sym})
                        )

                    async for message in ws:
                        try:
                            data = json.loads(message)
                            if data.get("type") == "trade" and on_tick:
                                for trade in data.get("data", []):
                                    tick = Tick(
                                        symbol=trade.get("s", ""),
                                        price=float(trade.get("p", 0)),
                                        size=float(trade.get("v", 0)),
                                        timestamp=datetime.fromtimestamp(
                                            trade.get("t", 0) / 1000,
                                            tz=timezone.utc,
                                        ),
                                        exchange=trade.get("x", ""),
                                    )
                                    if asyncio.iscoroutinefunction(on_tick):
                                        await on_tick(tick)
                                    else:
                                        on_tick(tick)
                        except Exception:
                            pass
            except Exception as exc:
                logger.error("Finnhub WebSocket error: %s", exc)
            finally:
                self._ws = None

        self._ws_task = asyncio.create_task(_ws_handler())

    async def disconnect_websocket(self) -> None:
        if self._ws_task and not self._ws_task.done():
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass
        if self._ws:
            await self._ws.close()
            self._ws = None
        self._ws_task = None
