"""
Emotion Display API — Market emotion data derived from technical indicators.
"""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
CREDENTIALS_FILE = BACKEND_DIR / "mt5_credentials.json"
DEFAULT_MT5_PATH = r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe"


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class EmotionResponse(BaseModel):
    symbol: str
    fear_greed_index: float
    emotion_state: str
    positioning: str
    social_score: float
    rsi: float
    adx: float
    bb_width: float
    timestamp: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_credentials() -> dict:
    if CREDENTIALS_FILE.exists():
        try:
            import json
            with open(CREDENTIALS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"login": int(os.environ.get("MT5_LOGIN", "0")), "password": os.environ.get("MT5_PASSWORD", ""), "server": os.environ.get("MT5_SERVER", ""), "mt5_path": DEFAULT_MT5_PATH}


def _get_mt5_data(symbol: str, timeframe, count: int = 200):
    """Fetch OHLC data from MT5 for the given symbol and timeframe."""
    import MetaTrader5 as mt5
    creds = _load_credentials()
    mt5_path = creds.get("mt5_path", DEFAULT_MT5_PATH)

    if not mt5.initialize(
        path=mt5_path,
        login=creds["login"],
        password=creds["password"],
        server=creds["server"],
    ):
        error = mt5.last_error()
        mt5.shutdown()
        raise RuntimeError(f"MT5 init failed: {error}")

    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
    mt5.shutdown()

    if rates is None or len(rates) == 0:
        raise RuntimeError(f"No data returned for {symbol}")

    return rates


def _compute_rsi(closes, period: int = 14) -> float:
    """Compute RSI from close prices."""
    if len(closes) < period + 1:
        return 50.0
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _compute_adx(highs, lows, closes, period: int = 14) -> float:
    """Compute Average Directional Index."""
    if len(closes) < period * 2:
        return 25.0

    plus_dm = []
    minus_dm = []
    tr_list = []

    for i in range(1, len(highs)):
        up_move = highs[i] - highs[i - 1]
        down_move = lows[i - 1] - lows[i]
        plus_dm.append(up_move if up_move > down_move and up_move > 0 else 0)
        minus_dm.append(down_move if down_move > up_move and down_move > 0 else 0)

        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        tr_list.append(tr)

    if len(tr_list) < period:
        return 25.0

    atr = sum(tr_list[:period]) / period
    plus_di_smooth = sum(plus_dm[:period]) / period
    minus_di_smooth = sum(minus_dm[:period]) / period

    dx_list = []
    for i in range(period, len(tr_list)):
        atr = (atr * (period - 1) + tr_list[i]) / period
        plus_di_smooth = (plus_di_smooth * (period - 1) + plus_dm[i]) / period
        minus_di_smooth = (minus_di_smooth * (period - 1) + minus_dm[i]) / period

        if atr == 0:
            continue
        plus_di = 100.0 * plus_di_smooth / atr
        minus_di = 100.0 * minus_di_smooth / atr
        di_sum = plus_di + minus_di
        if di_sum == 0:
            dx_list.append(0)
        else:
            dx_list.append(100.0 * abs(plus_di - minus_di) / di_sum)

    if not dx_list:
        return 25.0

    adx = sum(dx_list[:period]) / period
    for val in dx_list[period:]:
        adx = (adx * (period - 1) + val) / period
    return adx


def _compute_bollinger_width(closes, period: int = 20) -> float:
    """Compute Bollinger Band width (normalized as % of middle band)."""
    if len(closes) < period:
        return 0.02
    window = closes[-period:]
    sma = sum(window) / period
    variance = sum((x - sma) ** 2 for x in window) / period
    std = variance ** 0.5
    if sma == 0:
        return 0.02
    return (2 * std) / sma  # normalized width


def _map_emotion(fear_greed: float) -> str:
    if fear_greed < 10:
        return "Panic"
    elif fear_greed < 30:
        return "Fear"
    elif fear_greed < 50:
        return "Neutral"
    elif fear_greed < 70:
        return "Greed"
    else:
        return "Euphoria"


def _map_positioning(fear_greed: float, adx: float) -> str:
    if fear_greed < 30:
        return "OVERSOLD"
    elif fear_greed > 70:
        return "OVERBOUGHT"
    elif adx > 30:
        return "TRENDING"
    else:
        return "RANGING"


def _compute_fear_greed(rsi: float, adx: float, bb_width: float) -> float:
    """
    Compute Fear/Greed index (0-100):
    - RSI: oversold (30) = fear, overbought (70) = greed → direct mapping
    - ADX: trend strength = confidence → higher = greedier
    - BB Width: high volatility = panic → wider = more fear
    """
    # RSI component: map 20-80 range to 0-100
    rsi_score = max(0, min(100, (rsi - 20) * (100 / 60)))

    # ADX component: 0-50 mapped to 50-70 (trend = more greed/confidence)
    adx_score = 50 + min(20, adx * 0.4)

    # BB Width: wider bands = more fear (0.01=calm→60, 0.05=panic→10)
    bb_fear = max(0, min(100, 80 - bb_width * 2000))

    # Weighted average: RSI 50%, ADX 25%, BB 25%
    return max(0.0, min(100.0, rsi_score * 0.50 + adx_score * 0.25 + bb_fear * 0.25))


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

@router.get("/{symbol}")
def get_emotion(symbol: str):
    """Return market emotion data for a symbol."""
    import MetaTrader5 as mt5

    symbol = symbol.upper()

    try:
        rates = _get_mt5_data(symbol, mt5.TIMEFRAME_H1, 200)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"MT5 data fetch failed: {e}")

    closes = [r[4] for r in rates]
    highs = [r[2] for r in rates]
    lows = [r[3] for r in rates]

    rsi = _compute_rsi(closes)
    adx = _compute_adx(highs, lows, closes)
    bb_width = _compute_bollinger_width(closes)
    fear_greed = _compute_fear_greed(rsi, adx, bb_width)
    emotion_state = _map_emotion(fear_greed)
    positioning = _map_positioning(fear_greed, adx)

    # Social score: derived from RSI momentum (proxy for social sentiment)
    social_score = round(rsi * 0.7 + fear_greed * 0.3, 2)

    return EmotionResponse(
        symbol=symbol,
        fear_greed_index=round(fear_greed, 2),
        emotion_state=emotion_state,
        positioning=positioning,
        social_score=social_score,
        rsi=round(rsi, 2),
        adx=round(adx, 2),
        bb_width=round(bb_width, 6),
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
