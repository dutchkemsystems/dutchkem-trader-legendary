import json
import logging
import redis
from typing import Any, Optional
from django.conf import settings

logger = logging.getLogger(__name__)


class RedisCache:
    def __init__(self):
        self.client = redis.from_url(settings.REDIS_URL, decode_responses=True)

    def get(self, key: str) -> Optional[Any]:
        try:
            value = self.client.get(key)
            if value:
                return json.loads(value)
        except (redis.RedisError, json.JSONDecodeError) as e:
            logger.warning(f"Redis get failed for key {key}: {e}")
        return None

    def set(self, key: str, value: Any, ttl: int = 60):
        try:
            self.client.setex(key, ttl, json.dumps(value, default=str))
        except (redis.RedisError, TypeError) as e:
            logger.warning(f"Redis set failed for key {key}: {e}")

    def delete(self, key: str):
        try:
            self.client.delete(key)
        except redis.RedisError as e:
            logger.warning(f"Redis delete failed for key {key}: {e}")

    def get_market_data(self, symbol: str, timeframe: str) -> Optional[dict]:
        return self.get(f'market:{symbol}:{timeframe}')

    def set_market_data(self, symbol: str, timeframe: str, data: dict, ttl: int = 5):
        self.set(f'market:{symbol}:{timeframe}', data, ttl)

    def get_analyst_result(self, analyst_name: str, symbol: str, timeframe: str) -> Optional[dict]:
        return self.get(f'analyst:{analyst_name}:{symbol}:{timeframe}')

    def set_analyst_result(self, analyst_name: str, symbol: str, timeframe: str, data: dict, ttl: int = 30):
        self.set(f'analyst:{analyst_name}:{symbol}:{timeframe}', data, ttl)

    def get_consensus_result(self, symbol: str) -> Optional[dict]:
        return self.get(f'consensus:{symbol}')

    def set_consensus_result(self, symbol: str, data: dict, ttl: int = 10):
        self.set(f'consensus:{symbol}', data, ttl)

    def get_scan_result(self, symbol: str) -> Optional[dict]:
        return self.get(f'scan:{symbol}')

    def set_scan_result(self, symbol: str, data: dict, ttl: int = 15):
        self.set(f'scan:{symbol}', data, ttl)
