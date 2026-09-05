import pytest
from unittest.mock import patch, MagicMock
from cache.redis import RedisCache


def test_redis_cache_creation():
    with patch("redis.from_url") as mock_redis:
        mock_redis.return_value = MagicMock()
        cache = RedisCache()
        assert hasattr(cache, 'get')
        assert hasattr(cache, 'set')
        assert hasattr(cache, 'delete')


def test_redis_cache_set_get():
    with patch("redis.from_url") as mock_redis:
        mock_client = MagicMock()
        mock_redis.return_value = mock_client
        cache = RedisCache()

        cache.set("test_key", {"data": 123}, ttl=60)
        mock_client.setex.assert_called_once()

        mock_client.get.return_value = '{"data": 123}'
        result = cache.get("test_key")
        assert result == {"data": 123}


def test_redis_cache_delete():
    with patch("redis.from_url") as mock_redis:
        mock_client = MagicMock()
        mock_redis.return_value = mock_client
        cache = RedisCache()

        cache.delete("test_key")
        mock_client.delete.assert_called_once_with("test_key")


def test_redis_cache_get_none():
    with patch("redis.from_url") as mock_redis:
        mock_client = MagicMock()
        mock_client.get.return_value = None
        mock_redis.return_value = mock_client
        cache = RedisCache()

        result = cache.get("nonexistent")
        assert result is None


def test_market_data_cache():
    with patch("redis.from_url") as mock_redis:
        mock_client = MagicMock()
        mock_redis.return_value = mock_client
        cache = RedisCache()

        cache.set_market_data("EURUSD", "H1", {"price": 1.1234})
        mock_client.setex.assert_called_once()

        mock_client.get.return_value = '{"price": 1.1234}'
        result = cache.get_market_data("EURUSD", "H1")
        assert result == {"price": 1.1234}


def test_analyst_result_cache():
    with patch("redis.from_url") as mock_redis:
        mock_client = MagicMock()
        mock_redis.return_value = mock_client
        cache = RedisCache()

        cache.set_analyst_result("seykota", "EURUSD", "H1", {"trend": "BULLISH"})
        mock_client.setex.assert_called_once()

        mock_client.get.return_value = '{"trend": "BULLISH"}'
        result = cache.get_analyst_result("seykota", "EURUSD", "H1")
        assert result == {"trend": "BULLISH"}


def test_consensus_result_cache():
    with patch("redis.from_url") as mock_redis:
        mock_client = MagicMock()
        mock_redis.return_value = mock_client
        cache = RedisCache()

        cache.set_consensus_result("EURUSD", {"signal": "BUY"})
        mock_client.setex.assert_called_once()

        mock_client.get.return_value = '{"signal": "BUY"}'
        result = cache.get_consensus_result("EURUSD")
        assert result == {"signal": "BUY"}


def test_scan_result_cache():
    with patch("redis.from_url") as mock_redis:
        mock_client = MagicMock()
        mock_redis.return_value = mock_client
        cache = RedisCache()

        cache.set_scan_result("EURUSD", {"score": 85})
        mock_client.setex.assert_called_once()

        mock_client.get.return_value = '{"score": 85}'
        result = cache.get_scan_result("EURUSD")
        assert result == {"score": 85}
