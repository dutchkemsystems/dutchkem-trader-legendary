from fastapi import APIRouter
import MetaTrader5 as mt5
import numpy as np

router = APIRouter()

MT5_CONFIG = {
    "path": r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe",
    "login": 476963617,
    "password": "Christ@5436",
    "server": "Exness-MT5Trial9",
}


def _init_mt5():
    if not mt5.initialize(**MT5_CONFIG):
        error = mt5.last_error()
        raise RuntimeError(f"MT5 init failed: {error}")


def _shutdown_mt5():
    mt5.shutdown()


@router.get("/{symbol}/price")
async def get_price(symbol: str):
    _init_mt5()
    try:
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return {"error": f"No tick data for {symbol}"}
        info = mt5.symbol_info(symbol)
        return {
            "symbol": symbol,
            "bid": tick.bid,
            "ask": tick.ask,
            "spread": round(tick.ask - tick.bid, 5) if info else None,
            "point": info.point if info else None,
            "digits": info.digits if info else None,
            "volume": info.volume if info else None,
            "time": tick.time,
            "realtime": True,
        }
    finally:
        _shutdown_mt5()


@router.get("/{symbol}/analysis")
async def get_analysis(symbol: str, timeframe: str = "1H"):
    tf_map = {
        '1M': mt5.TIMEFRAME_M1, '5M': mt5.TIMEFRAME_M5, '15M': mt5.TIMEFRAME_M15,
        '1H': mt5.TIMEFRAME_H1, '4H': mt5.TIMEFRAME_H4, '1D': mt5.TIMEFRAME_D1,
    }
    mt5_tf = tf_map.get(timeframe, mt5.TIMEFRAME_H1)

    _init_mt5()
    try:
        rates = mt5.copy_rates_from_pos(symbol, mt5_tf, 0, 200)
        if rates is None or len(rates) < 50:
            return {"error": f"Insufficient data for {symbol} {timeframe}"}

        closes = np.array([r['close'] for r in rates], dtype=float)
        highs = np.array([r['high'] for r in rates], dtype=float)
        lows = np.array([r['low'] for r in rates], dtype=float)
        price = float(closes[-1])

        rsi = _compute_rsi(closes)
        macd_hist = _compute_macd_histogram(closes)
        sma20 = float(np.mean(closes[-20:])) if len(closes) >= 20 else price
        sma50 = float(np.mean(closes[-50:])) if len(closes) >= 50 else price

        score = 0
        if rsi < 35: score += 1
        elif rsi > 65: score -= 1
        if macd_hist > 0: score += 1
        elif macd_hist < 0: score -= 1
        if price > sma20 > sma50: score += 1
        elif price < sma20 < sma50: score -= 1

        if score >= 2: signal = 'BUY'
        elif score <= -2: signal = 'SELL'
        else: signal = 'HOLD'

        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "signal": signal,
            "confidence": min(abs(score) / 3.0, 1.0),
            "reasoning": {
                "rsi": round(rsi, 2),
                "macd_histogram": round(float(macd_hist), 8),
                "sma20": round(sma20, 5),
                "sma50": round(sma50, 5),
                "score": score,
            },
            "data": {
                "price": price,
                "high": float(highs[-1]),
                "low": float(lows[-1]),
                "candles": len(rates),
            },
        }
    finally:
        _shutdown_mt5()


def _compute_rsi(closes: np.ndarray, period: int = 14) -> float:
    deltas = np.diff(closes[-period - 1:])
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = float(np.mean(gains)) if len(gains) > 0 else 0.0
    avg_loss = float(np.mean(losses)) if len(losses) > 0 else 0.0
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _compute_macd_histogram(closes: np.ndarray) -> float:
    n = len(closes)
    ema12 = np.zeros(n)
    ema26 = np.zeros(n)
    k12 = 2.0 / 13.0
    k26 = 2.0 / 27.0
    ema12[0] = closes[0]
    ema26[0] = closes[0]
    for i in range(1, n):
        ema12[i] = closes[i] * k12 + ema12[i - 1] * (1 - k12)
        ema26[i] = closes[i] * k26 + ema26[i - 1] * (1 - k26)
    macd_line = ema12 - ema26
    signal = np.zeros(n)
    k9 = 2.0 / 10.0
    signal[0] = macd_line[0]
    for i in range(1, n):
        signal[i] = macd_line[i] * k9 + signal[i - 1] * (1 - k9)
    return float(macd_line[-1] - signal[-1])
