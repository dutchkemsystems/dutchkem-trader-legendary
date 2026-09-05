import json
import logging
from datetime import datetime
from typing import Any, Optional

from .models import Candle, Quote, Tick

logger = logging.getLogger(__name__)

CANDLE_TTL = 300
QUOTE_TTL = 10
TICK_TTL = 5


class DataCache:
    """In-memory TTL-based cache for market data objects.

    Uses a simple dict with timestamp-based expiry.
    Replace with Redis in production.
    """

    def __init__(self) -> None:
        self._store: dict[str, tuple[Any, float]] = {}

    def _make_key(self, *parts: str) -> str:
        return ":".join(parts)

    def _is_expired(self, key: str) -> bool:
        entry = self._store.get(key)
        if entry is None:
            return True
        _, expires_at = entry
        return datetime.now().timestamp() > expires_at

    def _set(self, key: str, value: Any, ttl: int) -> None:
        expires_at = datetime.now().timestamp() + ttl
        self._store[key] = (value, expires_at)

    def _get(self, key: str) -> Optional[Any]:
        if self._is_expired(key):
            self._store.pop(key, None)
            return None
        value, _ = self._store[key]
        return value

    def _delete(self, key: str) -> None:
        self._store.pop(key, None)

    def set_candle(self, symbol: str, timeframe: str, candle: Candle) -> None:
        key = self._make_key("candle", symbol, timeframe)
        self._set(key, candle, CANDLE_TTL)

    def get_candle(self, symbol: str, timeframe: str) -> Optional[Candle]:
        key = self._make_key("candle", symbol, timeframe)
        return self._get(key)

    def delete_candle(self, symbol: str, timeframe: str) -> None:
        key = self._make_key("candle", symbol, timeframe)
        self._delete(key)

    def set_quote(self, symbol: str, quote: Quote) -> None:
        key = self._make_key("quote", symbol)
        self._set(key, quote, QUOTE_TTL)

    def get_quote(self, symbol: str) -> Optional[Quote]:
        key = self._make_key("quote", symbol)
        return self._get(key)

    def set_tick(self, symbol: str, tick: Tick) -> None:
        key = self._make_key("tick", symbol)
        self._set(key, tick, TICK_TTL)

    def get_tick(self, symbol: str) -> Optional[Tick]:
        key = self._make_key("tick", symbol)
        return self._get(key)
