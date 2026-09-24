import json
import logging
import os
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)


class InMemoryCache:
    """In-memory fallback cache when Redis is unavailable."""

    def __init__(self):
        self._store: dict[str, tuple[Any, float]] = {}

    def get(self, key: str) -> Optional[Any]:
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if time.time() > expires_at:
            self._store.pop(key, None)
            return None
        return value

    def set(self, key: str, value: Any, ttl: int = 60):
        expires_at = time.time() + ttl
        self._store[key] = (value, expires_at)

    def delete(self, key: str):
        self._store.pop(key, None)


class RedisCache:
    def __init__(self):
        self._use_redis = True
        self._client = None
        try:
            import redis

            self._client = redis.from_url(
                os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            # Test connection
            self._client.ping()
            logger.info("Connected to Redis")
        except Exception as e:
            logger.warning(f"Redis not available, using in-memory cache: {e}")
            self._use_redis = False
            self._fallback = InMemoryCache()

    def _get_client(self):
        if not self._use_redis:
            return self._fallback
        return self._client

    def get(self, key: str) -> Optional[Any]:
        try:
            client = self._get_client()
            value = client.get(key)
            if value:
                if self._use_redis:
                    return json.loads(value)
                return value  # Already parsed in memory cache
        except Exception as e:
            logger.warning(f"Cache get failed for key {key}: {e}")
        return None

    def set(self, key: str, value: Any, ttl: int = 60):
        try:
            client = self._get_client()
            if self._use_redis:
                client.setex(key, ttl, json.dumps(value, default=str))
            else:
                client.set(key, value, ttl)
        except Exception as e:
            logger.warning(f"Cache set failed for key {key}: {e}")

    def delete(self, key: str):
        try:
            client = self._get_client()
            client.delete(key)
        except Exception as e:
            logger.warning(f"Cache delete failed for key {key}: {e}")

    def get_market_data(self, symbol: str, timeframe: str) -> Optional[dict]:
        return self.get(f"market:{symbol}:{timeframe}")

    def set_market_data(self, symbol: str, timeframe: str, data: dict, ttl: int = 5):
        self.set(f"market:{symbol}:{timeframe}", data, ttl)

    def get_analyst_result(
        self, analyst_name: str, symbol: str, timeframe: str
    ) -> Optional[dict]:
        return self.get(f"analyst:{analyst_name}:{symbol}:{timeframe}")

    def set_analyst_result(
        self, analyst_name: str, symbol: str, timeframe: str, data: dict, ttl: int = 30
    ):
        self.set(f"analyst:{analyst_name}:{symbol}:{timeframe}", data, ttl)

    def get_consensus_result(self, symbol: str) -> Optional[dict]:
        return self.get(f"consensus:{symbol}")

    def set_consensus_result(self, symbol: str, data: dict, ttl: int = 10):
        self.set(f"consensus:{symbol}", data, ttl)

    def get_scan_result(self, symbol: str) -> Optional[dict]:
        return self.get(f"scan:{symbol}")

    def set_scan_result(self, symbol: str, data: dict, ttl: int = 15):
        self.set(f"scan:{symbol}", data, ttl)
