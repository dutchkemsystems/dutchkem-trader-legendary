from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Callable

try:
    import akshare as akshare  # noqa: F401
except ImportError:
    akshare = None  # type: ignore[assignment,misc]

from data.models import Candle, Quote, Tick, Timeframe
from data.providers import BaseDataProvider

logger = logging.getLogger(__name__)

# Mapping from our Timeframe enum to akshare period strings
_TIMEFRAME_MAP: dict[Timeframe, str] = {
    Timeframe.ONE_MINUTE: "1",
    Timeframe.FIVE_MINUTES: "5",
    Timeframe.FIFTEEN_MINUTES: "15",
    Timeframe.ONE_HOUR: "60",
    Timeframe.FOUR_HOURS: "240",
    Timeframe.ONE_DAY: "daily",
}


class AKShareProvider(BaseDataProvider):
    """Zero-cost data provider backed by AKShare.

    Supports forex (via Sina) and US/CN equities.
    No API key required. Rate limits are soft (polite usage).
    """

    name: str = "akshare"

    async def get_candles(
        self, symbol: str, timeframe: Timeframe, limit: int = 100
    ) -> list[Candle]:
        if akshare is None:
            raise ImportError("akshare is not installed")

        try:
            df = self._fetch_history(symbol, timeframe, limit)
            candles: list[Candle] = []
            for _, row in df.iterrows():
                ts = row.get("Datetime") or row.get("日期") or datetime.utcnow()
                if isinstance(ts, str):
                    try:
                        ts = datetime.fromisoformat(ts)
                    except (ValueError, TypeError):
                        ts = datetime.utcnow()
                candles.append(
                    Candle(
                        symbol=symbol,
                        timeframe=timeframe,
                        open=float(row.get("Open", row.get("开盘", 0))),
                        high=float(row.get("High", row.get("最高", 0))),
                        low=float(row.get("Low", row.get("最低", 0))),
                        close=float(row.get("Close", row.get("收盘", 0))),
                        volume=int(row.get("Volume", row.get("成交量", 0))),
                        timestamp=ts,
                    )
                )
            return candles
        except Exception:
            logger.exception("AKShare get_candles failed for %s", symbol)
            raise  # Let registry fall back to next provider

    async def get_latest_price(self, symbol: str) -> float:
        if akshare is None:
            raise ImportError("akshare is not installed")

        try:
            df = self._fetch_history(symbol, Timeframe.ONE_DAY, limit=1)
            if len(df) > 0:
                last = df.iloc[-1]
                return float(last.get("Close", last.get("收盘", 0.0)))
        except Exception:
            logger.exception("AKShare get_latest_price failed for %s", symbol)

        raise RuntimeError(f"AKShare could not get latest price for {symbol}")

    async def get_quote(self, symbol: str) -> Quote:
        if akshare is None:
            raise ImportError("akshare is not installed")

        try:
            spot = akshare.forex_spot()
            row = spot[spot["货币对"] == symbol]
            if len(row) > 0:
                r = row.iloc[0]
                bid = float(r.get("买入价", 0))
                ask = float(r.get("卖出价", 0))
                return Quote(
                    symbol=symbol,
                    bid=bid,
                    ask=ask,
                    bid_size=0,
                    ask_size=0,
                    timestamp=datetime.utcnow(),
                )
        except Exception:
            logger.exception("AKShare get_quote failed for %s", symbol)

        return Quote(
            symbol=symbol,
            bid=0.0,
            ask=0.0,
            bid_size=0,
            ask_size=0,
            timestamp=datetime.utcnow(),
        )

    async def get_ticks(self, symbol: str, limit: int = 100) -> list[Tick]:
        return []

    async def connect_websocket(
        self, symbols: list[str], on_tick: Callable[[Tick], Any] | None = None
    ) -> None:
        logger.info("AKShare does not support WebSocket — connect_websocket is a no-op")

    async def disconnect_websocket(self) -> None:
        pass

    # ── Private helpers ───────────────────────────────────────────────────

    def _is_forex(self, symbol: str) -> bool:
        forex_pairs = {
            "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD",
            "NZDUSD", "EURGBP", "EURJPY", "GBPJPY", "AUDJPY", "EURAUD",
            "EURCHF", "GBPCHF", "USDSEK", "USDNOK", "USDSGD", "USDHKD",
            "USDMXN", "USDZAR", "USDTRY", "USDCNH", "USDTWD", "USDTHB",
            "USDKRW", "EURUSD=X", "GBPUSD=X", "USDJPY=X",
        }
        return symbol.upper().replace("/", "") in forex_pairs or "X" in symbol.upper()

    def _fetch_history(self, symbol: str, timeframe: Timeframe, limit: int) -> Any:
        if akshare is None:
            raise ImportError("akshare is not installed")

        if self._is_forex(symbol):
            clean = symbol.replace("=X", "").replace("/", "")
            period = _TIMEFRAME_MAP.get(timeframe, "daily")
            df = akshare.forex_hist_sina(symbol=f"fx_s{clean.lower()}")
            if df is not None and len(df) > limit:
                df = df.tail(limit)
            return df
        else:
            end = datetime.now()
            start = end - timedelta(days=max(limit, 30))
            df = akshare.stock_zh_a_hist(
                symbol=symbol,
                period="daily",
                start_date=start.strftime("%Y%m%d"),
                end_date=end.strftime("%Y%m%d"),
                adjust="qfq",
            )
            if df is not None and len(df) > limit:
                df = df.tail(limit)
            return df
