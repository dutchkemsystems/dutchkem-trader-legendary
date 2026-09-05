import pandas as pd
from typing import Dict, Any, Optional

class TurtleSoupModule:
    def __init__(self):
        self.lookback = 20
        self.breakout_range = 0.002

    def detect_false_breakout(self, data: pd.DataFrame) -> Optional[Dict[str, Any]]:
        if len(data) < self.lookback + 1:
            return None

        # 1. Get recent high/low
        high = data['high'].rolling(self.lookback).max()
        low = data['low'].rolling(self.lookback).min()

        # 2. Check breakout
        current_close = data['close'].iloc[-1]
        previous_close = data['close'].iloc[-2]

        # 3. Bullish false breakout
        if current_close > high.iloc[-2] and previous_close < high.iloc[-2]:
            if current_close < high.iloc[-2] + self.breakout_range:
                return {
                    'signal': 'BUY',
                    'confidence': 0.75,
                    'reason': 'Bullish Turtle Soup'
                }

        # 4. Bearish false breakout
        if current_close < low.iloc[-2] and previous_close > low.iloc[-2]:
            if current_close > low.iloc[-2] - self.breakout_range:
                return {
                    'signal': 'SELL',
                    'confidence': 0.75,
                    'reason': 'Bearish Turtle Soup'
                }

        return None
