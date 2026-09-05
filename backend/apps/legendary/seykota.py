import pandas as pd
import numpy as np
from typing import Dict, Any

class SeykotaTrendModule:
    def __init__(self):
        self.ema_periods = [21, 50, 200]
        self.adx_threshold = 20

    def analyze_trend(self, data: pd.DataFrame) -> Dict[str, Any]:
        close = data['close']

        # Calculate EMAs
        ema21 = close.ewm(span=21).mean()
        ema50 = close.ewm(span=50).mean()
        ema200 = close.ewm(span=200).mean()

        # Determine trend direction
        if ema21.iloc[-1] > ema50.iloc[-1] > ema200.iloc[-1]:
            trend = 'BULLISH'
        elif ema21.iloc[-1] < ema50.iloc[-1] < ema200.iloc[-1]:
            trend = 'BEARISH'
        else:
            trend = 'NEUTRAL'

        # Calculate ADX (simplified)
        adx = self._calculate_adx(data)

        # Block chop (ADX < 20)
        if adx < self.adx_threshold:
            return {
                'trend': 'CHOP',
                'confidence': 0,
                'action': 'HOLD',
                'adx': adx
            }

        # Generate signal
        if trend == 'BULLISH':
            return {
                'trend': 'BULLISH',
                'confidence': min(1.0, adx / 50),
                'action': 'BUY',
                'adx': adx
            }
        elif trend == 'BEARISH':
            return {
                'trend': 'BEARISH',
                'confidence': min(1.0, adx / 50),
                'action': 'SELL',
                'adx': adx
            }

        return {
            'trend': 'NEUTRAL',
            'confidence': 0,
            'action': 'HOLD',
            'adx': adx
        }

    def _calculate_adx(self, data: pd.DataFrame, period: int = 14) -> float:
        high = data['high']
        low = data['low']
        close = data['close']

        plus_dm = high.diff()
        minus_dm = -low.diff()

        plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
        minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)

        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        atr = tr.rolling(window=period).mean()
        plus_di = 100 * (plus_dm.rolling(window=period).mean() / atr)
        minus_di = 100 * (minus_dm.rolling(window=period).mean() / atr)

        dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di))
        adx = dx.rolling(window=period).mean()

        return float(adx.iloc[-1]) if not pd.isna(adx.iloc[-1]) else 0.0
