from fastapi import APIRouter
from api.deps import get_scanner

router = APIRouter()


@router.get("/{symbol}")
async def scan_symbol(symbol: str):
    scanner = get_scanner()
    result = await scanner.scan(symbol)
    return {
        "symbol": result.symbol,
        "h1_bias": result.h1_bias,
        "alignment": result.alignment,
        "overall_signal": result.overall_signal,
        "overall_confidence": result.overall_confidence,
        "timeframes": {tf: {"signal": r.signal, "confidence": r.confidence, "data": getattr(r, 'data', {})} for tf, r in result.timeframes.items()}
    }


@router.get("/{symbol}/timeframe/{timeframe}")
async def scan_timeframe(symbol: str, timeframe: str):
    scanner = get_scanner()
    result = await scanner.scan(symbol)
    tf_result = result.timeframes.get(timeframe)
    if not tf_result:
        return {"error": f"Timeframe {timeframe} not found"}
    return {"symbol": symbol, "timeframe": timeframe, "signal": tf_result.signal, "confidence": tf_result.confidence, "data": tf_result.data}
