from datetime import datetime
from typing import Any

from .models import Candle, Quote, Tick, Timeframe


class DataNormalizer:
    """Normalizes raw provider data into standard model objects.

    Supports Polygon.io, yfinance, and AKShare providers.
    Each provider uses different field names and formats.
    """

    def normalize_candle(
        self,
        data: dict[str, Any],
        symbol: str,
        timeframe: Timeframe,
        provider: str = "polygon",
    ) -> Candle:
        if provider == "polygon":
            safe_data = dict(data)
            if "t" not in safe_data:
                safe_data["t"] = int(datetime.now().timestamp() * 1000)
            return Candle.from_polygon(safe_data, symbol, timeframe)
        elif provider == "yfinance":
            return Candle.from_yfinance(data, symbol, timeframe)
        elif provider == "akshare":
            return Candle.from_akshare(data, symbol, timeframe)
        else:
            raise ValueError(f"Unknown provider: {provider}")

    def normalize_quote(
        self,
        data: dict[str, Any],
        symbol: str,
        provider: str = "polygon",
    ) -> Quote:
        if provider == "polygon":
            return Quote.from_polygon(data, symbol)
        else:
            raise ValueError(f"Unknown provider: {provider}")

    def normalize_tick(
        self,
        data: dict[str, Any],
        provider: str = "polygon",
    ) -> Tick:
        if provider == "polygon":
            return Tick.from_polygon(data)
        else:
            raise ValueError(f"Unknown provider: {provider}")

    def normalize_batch_candles(
        self,
        data_list: list[dict[str, Any]],
        symbol: str,
        timeframe: Timeframe,
        provider: str = "polygon",
    ) -> list[Candle]:
        return [
            self.normalize_candle(d, symbol, timeframe, provider)
            for d in data_list
        ]
