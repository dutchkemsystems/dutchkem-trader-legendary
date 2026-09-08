from fastapi import APIRouter
from api.deps import get_consensus_engine, get_consensus_gates, get_ml_predictor, get_market_data_manager
from apps.vision import ChartAnalyzer
from apps.consensus.black_scholes import BlackScholesEngine
from apps.consensus.regime import MarketRegimeDetector

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


@router.get("/{symbol}/full")
async def get_full_consensus(
    symbol: str,
    timeframe: str = "1H",
):
    """Full V5 consensus: debate + memory + gates + ML."""
    engine = get_consensus_engine()
    result = await engine.evaluate(symbol, timeframe, use_debate=True, use_memory=True)

    # Build signal counts from analyst votes
    analyst_votes = result.get("votes", {})
    vote_counts = {"BUY": 0, "SELL": 0, "HOLD": 0}
    for signal in analyst_votes.values():
        if signal in vote_counts:
            vote_counts[signal] += 1
    result["votes"] = vote_counts

    # Run 7 gates
    gates = get_consensus_gates()
    regime_detector = MarketRegimeDetector()
    black_scholes = BlackScholesEngine()
    gates.black_scholes = black_scholes
    gates.regime_detector = regime_detector

    gate_result = gates.evaluate_all(
        consensus={"agreement_pct": result.get("agreement_pct", 0)},
        analyst_results=[],
        p_up=0.5,
        market_price=0.5,
        risk_status={"max_positions": 10, "current_positions": 0},
    )
    result["gates"] = gate_result
    return result


@router.get("/{symbol}/debate")
async def get_debate(symbol: str):
    """Run Bull vs Bear debate on symbol."""
    engine = get_consensus_engine()
    if not engine.debate_engine:
        return {"error": "Debate engine not configured"}
    try:
        debate_result = await engine.debate_engine.debate(symbol)
        return {
            "symbol": symbol,
            "winner": debate_result.winner,
            "bull_confidence": debate_result.bull_confidence,
            "bear_confidence": debate_result.bear_confidence,
            "rounds": debate_result.rounds,
        }
    except Exception as e:
        return {"symbol": symbol, "error": str(e)}


@router.get("/{symbol}/memory")
async def get_memory(symbol: str, timeframe: str = "1H"):
    """Retrieve similar past situations from memory."""
    engine = get_consensus_engine()
    if not engine.memory:
        return {"symbol": symbol, "similar_situations": []}
    try:
        similar = engine.memory.retrieve(f"{symbol} {timeframe}")
        return {
            "symbol": symbol,
            "similar_situations": [
                {
                    "symbol": s.symbol,
                    "situation": s.situation,
                    "outcome": s.outcome,
                    "lesson": s.lesson,
                    "relevance_score": s.relevance_score,
                }
                for s in similar
            ],
        }
    except Exception as e:
        return {"symbol": symbol, "similar_situations": [], "error": str(e)}


@router.get("/{symbol}/history")
async def get_consensus_history(symbol: str):
    # Placeholder: will query database
    return {"symbol": symbol, "history": []}
