from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, Dict, Any


@dataclass
class AnalystResult:
    analyst_name: str
    symbol: str
    timeframe: str
    signal: Literal["BUY", "SELL", "HOLD"]
    confidence: float
    reasoning: str
    data: Dict[str, Any]
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc)
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("Confidence must be between 0.0 and 1.0")
        if self.signal not in ("BUY", "SELL", "HOLD"):
            raise ValueError("Signal must be BUY, SELL, or HOLD")


class BaseAnalyst(ABC):
    @abstractmethod
    async def analyze(self, symbol: str, timeframe: str) -> AnalystResult:
        pass

    @abstractmethod
    def get_capabilities(self) -> list[str]:
        pass
