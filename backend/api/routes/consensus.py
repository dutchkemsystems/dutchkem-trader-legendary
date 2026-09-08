from fastapi import APIRouter
from api.deps import get_consensus_engine

router = APIRouter()


@router.get("/{symbol}")
async def get_consensus(
    symbol: str,
    timeframe: str = "1H",
    use_debate: bool = False,
    use_memory: bool = False,
):
    engine = get_consensus_engine()
    result = await engine.evaluate(symbol, timeframe, use_debate=use_debate, use_memory=use_memory)

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
