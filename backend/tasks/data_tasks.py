from __future__ import annotations

import asyncio
import logging

from celery import shared_task

from data.models import Timeframe
from data.manager import MarketDataManager

logger = logging.getLogger(__name__)

_manager: MarketDataManager | None = None


def _get_manager() -> MarketDataManager:
    global _manager
    if _manager is None:
        _manager = MarketDataManager()
    return _manager


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@shared_task
def fetch_candles_task(symbol: str, timeframe: str, limit: int = 100):
    try:
        tf = Timeframe(timeframe)
        manager = _get_manager()
        candles = _run_async(manager.get_candles(symbol, tf, limit))
        return [c.to_dict() for c in candles]
    except Exception as e:
        logger.error("fetch_candles_task failed: %s", e)
        return {"error": str(e)}


@shared_task
def fetch_quote_task(symbol: str):
    try:
        manager = _get_manager()
        quote = _run_async(manager.get_quote(symbol))
        return {
            "symbol": quote.symbol,
            "bid": quote.bid,
            "ask": quote.ask,
            "bid_size": quote.bid_size,
            "ask_size": quote.ask_size,
            "spread": quote.spread,
            "timestamp": quote.timestamp.isoformat() if hasattr(quote.timestamp, "isoformat") else str(quote.timestamp),
        }
    except Exception as e:
        logger.error("fetch_quote_task failed: %s", e)
        return {"error": str(e)}


@shared_task
def fetch_latest_price_task(symbol: str):
    try:
        manager = _get_manager()
        return _run_async(manager.get_latest_price(symbol))
    except Exception as e:
        logger.error("fetch_latest_price_task failed: %s", e)
        return {"error": str(e)}
