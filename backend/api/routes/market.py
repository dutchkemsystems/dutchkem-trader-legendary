from fastapi import APIRouter, HTTPException
from apps.analysts.market import MarketAnalyst
from cache.redis import RedisCache
from api.deps import get_market_analyst, get_redis_cache

router = APIRouter()


@router.get("/{symbol}/price")
async def get_price(symbol: str):
    cache = get_redis_cache()
    cached = cache.get_market_data(symbol, "1H")
    if cached:
        return cached

    analyst = get_market_analyst()
    result = await analyst.analyze(symbol, "1H")

    response = {"symbol": symbol, "signal": result.signal, "confidence": result.confidence, "data": result.data}
    cache.set_market_data(symbol, "1H", response, ttl=5)
    return response


@router.get("/{symbol}/analysis")
async def get_analysis(symbol: str, timeframe: str = "1H"):
    analyst = get_market_analyst()
    result = await analyst.analyze(symbol, timeframe)
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "signal": result.signal,
        "confidence": result.confidence,
        "reasoning": result.reasoning,
        "data": result.data
    }
