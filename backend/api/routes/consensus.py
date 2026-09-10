from fastapi import APIRouter
from api.deps import get_consensus_engine, get_consensus_gates, get_ml_predictor, get_market_data_manager
from apps.vision import ChartAnalyzer
from apps.consensus.black_scholes import BlackScholesEngine
from apps.consensus.regime import MarketRegimeDetector
from apps.ml.features import FeatureExtractor
from data.mt5_fetcher import async_fetch_mt5_candles, async_fetch_mt5_price
import numpy as np
import logging

logger = logging.getLogger(__name__)

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

    # --- Fetch real data for ML + gates ---
    p_up = 0.5
    market_price = 0.5
    ml_status = "not_available"
    features_used = 0
    real_features = []

    df = await async_fetch_mt5_candles(symbol, timeframe, 200)
    if df is not None and len(df) >= FeatureExtractor.MIN_ROWS:
        extractor = FeatureExtractor()
        try:
            features_df = extractor.extract(df)
            if len(features_df) > 0:
                last_row = features_df.iloc[[-1]].values
                real_features = last_row.tolist()
                ml_predictor = get_ml_predictor()
                ml_pred = ml_predictor.predict_from_features(last_row)
                p_up = ml_pred.p_up
                features_used = ml_pred.features_used
                ml_status = f"{ml_pred.model_name}_trained={ml_predictor.is_trained}"
                logger.info("ML P(UP) for %s: %.4f (%s)", symbol, p_up, ml_status)
        except Exception as e:
            logger.warning("ML prediction failed for %s: %s", symbol, e)
            ml_status = f"error: {e}"

    price_data = await async_fetch_mt5_price(symbol)
    if price_data:
        market_price = price_data["bid"]
    else:
        market_price = df["close"].iloc[-1] if df is not None and len(df) > 0 else 0.5

    result["ml"] = {
        "p_up": round(p_up, 4),
        "market_price": market_price,
        "status": ml_status,
        "features_used": features_used,
        "model_trained": get_ml_predictor().is_trained,
    }

    # Run 7 gates with real P(UP) and market price
    gates = get_consensus_gates()
    regime_detector = MarketRegimeDetector()
    black_scholes = BlackScholesEngine()
    gates.black_scholes = black_scholes
    gates.regime_detector = regime_detector

    gate_result = gates.evaluate_all(
        consensus={"agreement_pct": result.get("agreement_pct", 0)},
        analyst_results=[],
        features=real_features,
        p_up=p_up,
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
