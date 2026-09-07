from fastapi import APIRouter
from api.deps import get_consensus_engine

router = APIRouter()


@router.get("/{symbol}")
async def get_consensus(symbol: str, timeframe: str = "1H"):
    engine = get_consensus_engine()
    result = await engine.evaluate(symbol, timeframe)

    # Build signal counts from analyst votes
    analyst_votes = result.get("votes", {})
    vote_counts = {"BUY": 0, "SELL": 0, "HOLD": 0}
    for signal in analyst_votes.values():
        if signal in vote_counts:
            vote_counts[signal] += 1

    result["votes"] = vote_counts
    return result


@router.get("/{symbol}/history")
async def get_consensus_history(symbol: str):
    # Placeholder: will query database
    return {"symbol": symbol, "history": []}
