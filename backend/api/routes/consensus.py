from fastapi import APIRouter
from api.deps import get_consensus_engine

router = APIRouter()


@router.get("/{symbol}")
async def get_consensus(symbol: str, timeframe: str = "1H"):
    engine = get_consensus_engine()
    result = await engine.evaluate(symbol, timeframe)
    return result


@router.get("/{symbol}/history")
async def get_consensus_history(symbol: str):
    # Placeholder: will query database
    return {"symbol": symbol, "history": []}
