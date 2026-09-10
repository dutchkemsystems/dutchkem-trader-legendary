"""LLM API routes — Ollama integration for trading analysis."""
from fastapi import APIRouter
from api.deps import get_llm_client
from data.mt5_fetcher import async_fetch_mt5_candles, async_fetch_mt5_price
from apps.ml.features import FeatureExtractor
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/status")
async def get_llm_status():
    """Get LLM provider status and available models."""
    client = get_llm_client()
    return client.provider_status


@router.get("/analyze/{symbol}")
async def analyze_symbol(
    symbol: str,
    timeframe: str = "H1",
    task: str = "analysis",
):
    """Run LLM analysis on a symbol."""
    client = get_llm_client()

    # Fetch candles
    df = await async_fetch_mt5_candles(symbol, timeframe, 100)
    if df is None or len(df) < 20:
        return {"error": "Insufficient data", "symbol": symbol}

    # Extract indicators
    extractor = FeatureExtractor()
    features_df = extractor.extract(df)
    if len(features_df) == 0:
        return {"error": "Could not extract features", "symbol": symbol}

    last = features_df.iloc[-1]
    indicators = {
        "close": float(last.get("close", 0)),
        "rsi": float(last.get("rsi", 50)),
        "macd_hist": float(last.get("macd_hist", 0)),
        "adx": float(last.get("adx", 0)),
        "plus_di": float(last.get("plus_di", 0)),
        "minus_di": float(last.get("minus_di", 0)),
        "atr": float(last.get("atr", 0)),
        "ema_21": float(last.get("ema_21", 0)),
        "sma_50": float(last.get("sma_50", 0)),
        "bb_width": float(last.get("bb_width", 0)),
        "tenkan": float(last.get("tenkan", 0)),
        "kijun": float(last.get("kijun", 0)),
        "senkou_a": float(last.get("senkou_a", 0)),
        "senkou_b": float(last.get("senkou_b", 0)),
        "vol_ratio": float(last.get("volume_ratio", 1)),
    }

    if task == "analysis":
        result = client.analyze_trading_signal(symbol, timeframe, indicators)
    elif task == "risk":
        result = client.assess_risk(
            symbol=symbol, direction="BUY", score=0, atr=indicators["atr"],
            volatility=0.01, current_positions=0, max_positions=3,
            balance=10000, drawdown_pct=0,
        )
    else:
        result = client.analyze(f"Analyze {symbol} with task: {task}", task=task)

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "task": task,
        "signal": result.parsed.get("signal", "HOLD"),
        "confidence": result.parsed.get("confidence", result.confidence),
        "reasoning": result.parsed.get("reasoning", result.text[:500]),
        "model_used": result.model_used,
        "key_levels": result.parsed.get("key_levels", {}),
    }


@router.get("/debate/{symbol}")
async def llm_debate(symbol: str, timeframe: str = "H1"):
    """Run LLM-powered bull vs bear debate."""
    client = get_llm_client()

    # Fetch candles
    df = await async_fetch_mt5_candles(symbol, timeframe, 100)
    if df is None or len(df) < 20:
        return {"error": "Insufficient data", "symbol": symbol}

    # Extract indicators
    extractor = FeatureExtractor()
    features_df = extractor.extract(df)
    if len(features_df) == 0:
        return {"error": "Could not extract features", "symbol": symbol}

    last = features_df.iloc[-1]
    indicators = {
        "close": float(last.get("close", 0)),
        "rsi": float(last.get("rsi", 50)),
        "macd_hist": float(last.get("macd_hist", 0)),
        "adx": float(last.get("adx", 0)),
        "ema_21": float(last.get("ema_21", 0)),
        "sma_50": float(last.get("sma_50", 0)),
        "volume_ratio": float(last.get("volume_ratio", 1)),
        "senkou_a": float(last.get("senkou_a", 0)),
    }

    # Run bull and bear arguments
    bull = client.analyze_debate(symbol, "BULL", indicators)
    bear = client.analyze_debate(symbol, "BEAR", indicators)

    bull_conf = bull.parsed.get("confidence", bull.confidence)
    bear_conf = bear.parsed.get("confidence", bear.confidence)

    if bull_conf > bear_conf + 0.1:
        winner = "BULL"
    elif bear_conf > bull_conf + 0.1:
        winner = "BEAR"
    else:
        winner = "NEUTRAL"

    return {
        "symbol": symbol,
        "winner": winner,
        "bull_confidence": round(bull_conf, 3),
        "bear_confidence": round(bear_conf, 3),
        "bull_reasoning": bull.parsed.get("reasoning", bull.text[:300]),
        "bear_reasoning": bear.parsed.get("reasoning", bear.text[:300]),
        "bull_evidence": bull.parsed.get("key_evidence", []),
        "bear_evidence": bear.parsed.get("key_evidence", []),
        "models_used": [bull.model_used, bear.model_used],
    }


@router.get("/consensus/{symbol}")
async def llm_multi_model_consensus(symbol: str, timeframe: str = "H1"):
    """Run multi-model Ollama consensus."""
    client = get_llm_client()

    # Fetch candles
    df = await async_fetch_mt5_candles(symbol, timeframe, 100)
    if df is None or len(df) < 20:
        return {"error": "Insufficient data", "symbol": symbol}

    # Extract indicators
    extractor = FeatureExtractor()
    features_df = extractor.extract(df)
    if len(features_df) == 0:
        return {"error": "Could not extract features", "symbol": symbol}

    last = features_df.iloc[-1]
    indicators = {
        "close": float(last.get("close", 0)),
        "rsi": float(last.get("rsi", 50)),
        "macd_hist": float(last.get("macd_hist", 0)),
        "adx": float(last.get("adx", 0)),
        "plus_di": float(last.get("plus_di", 0)),
        "minus_di": float(last.get("minus_di", 0)),
        "atr": float(last.get("atr", 0)),
        "ema_21": float(last.get("ema_21", 0)),
        "sma_50": float(last.get("sma_50", 0)),
        "bb_width": float(last.get("bb_width", 0)),
        "tenkan": float(last.get("tenkan", 0)),
        "kijun": float(last.get("kijun", 0)),
        "senkou_a": float(last.get("senkou_a", 0)),
        "senkou_b": float(last.get("senkou_b", 0)),
        "vol_ratio": float(last.get("volume_ratio", 1)),
    }

    result = client.get_multi_model_consensus(symbol, indicators)
    result["symbol"] = symbol
    result["timeframe"] = timeframe
    return result
