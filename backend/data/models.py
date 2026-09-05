from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from typing import Any


class Timeframe(Enum):
    ONE_MINUTE = "1M"
    FIVE_MINUTES = "5M"
    FIFTEEN_MINUTES = "15M"
    ONE_HOUR = "1H"
    FOUR_HOURS = "4H"
    ONE_DAY = "1D"


@dataclass
class Candle:
    symbol: str
    timeframe: Timeframe
    open: float
    high: float
    low: float
    close: float
    volume: int | float
    timestamp: datetime

    def __post_init__(self) -> None:
        if self.high < self.low:
            raise ValueError(
                f"high ({self.high}) must be >= low ({self.low})"
            )
        if self.high < self.open or self.high < self.close:
            raise ValueError(
                f"high ({self.high}) must be >= open ({self.open}) and close ({self.close})"
            )
        if self.low > self.open or self.low > self.close:
            raise ValueError(
                f"low ({self.low}) must be <= open ({self.open}) and close ({self.close})"
            )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_polygon(cls, data: dict[str, Any], symbol: str, timeframe: Timeframe) -> Candle:
        return cls(
            symbol=symbol,
            timeframe=timeframe,
            open=float(data["o"]),
            high=float(data["h"]),
            low=float(data["l"]),
            close=float(data["c"]),
            volume=int(data["v"]),
            timestamp=datetime.fromtimestamp(data["t"] / 1000),
        )

    @classmethod
    def from_yfinance(cls, data: dict[str, Any], symbol: str, timeframe: Timeframe) -> Candle:
        return cls(
            symbol=symbol,
            timeframe=timeframe,
            open=float(data["Open"]),
            high=float(data["High"]),
            low=float(data["Low"]),
            close=float(data["Close"]),
            volume=int(data["Volume"]),
            timestamp=data.name.to_pydatetime() if hasattr(data, "name") else datetime.utcnow(),
        )

    @classmethod
    def from_akshare(cls, data: dict[str, Any], symbol: str, timeframe: Timeframe) -> Candle:
        return cls(
            symbol=symbol,
            timeframe=timeframe,
            open=float(data["open"]),
            high=float(data["high"]),
            low=float(data["low"]),
            close=float(data["close"]),
            volume=int(data["volume"]),
            timestamp=data.get("datetime", datetime.utcnow()),
        )


@dataclass
class Tick:
    symbol: str
    price: float
    size: int | float
    timestamp: datetime
    exchange: str = ""

    @classmethod
    def from_polygon(cls, data: dict[str, Any]) -> Tick:
        return cls(
            symbol=data.get("sym", ""),
            price=float(data.get("p", 0)),
            size=float(data.get("s", 0)),
            timestamp=datetime.fromtimestamp(data.get("t", 0) / 1000),
            exchange=data.get("x", ""),
        )


@dataclass
class Quote:
    symbol: str
    bid: float
    ask: float
    bid_size: int | float
    ask_size: int | float
    timestamp: datetime

    @property
    def spread(self) -> float:
        return round(self.ask - self.bid, 10)

    @classmethod
    def from_polygon(cls, data: dict[str, Any], symbol: str) -> Quote:
        return cls(
            symbol=symbol,
            bid=float(data.get("bp", 0)),
            ask=float(data.get("ap", 0)),
            bid_size=float(data.get("bs", 0)),
            ask_size=float(data.get("as", 0)),
            timestamp=datetime.fromtimestamp(data.get("t", 0) / 1000),
        )
