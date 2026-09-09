"""
Paul Tudor Jones - Macro Timing & Risk Management
"The secret to being successful from a trading perspective is to have an indefatigable thirst for information."
"""
import pandas as pd
import numpy as np
from typing import Dict, Any

class TudorJonesAgent:
    def __init__(self):
        self.name = "Paul Tudor Jones"
        self.philosophy = "Macro Timing + Aggressive Risk Management"
        self.specialties = ["macro_timing", "risk_management", "pattern_recognition"]
        self.risk_tolerance = 0.75
        self.max_position = 0.15

    def analyze(self, data: pd.DataFrame, symbol: str) -> Dict[str, Any]:
        try:
            close = data['close'].dropna()
            high = data['high'].dropna()
            low = data['low'].dropna()
            
            if len(close) < 21:
                return self._empty(symbol, "Insufficient data")
            
            ema8 = close.ewm(span=8).mean()
            ema21 = close.ewm(span=21).mean()
            
            macd_line = ema8 - ema21
            signal_line = macd_line.ewm(span=9).mean()
            macd_hist = macd_line - signal_line
            macd_current = float(macd_hist.iloc[-1])
            macd_prev = float(macd_hist.iloc[-2])
            
            delta = close.diff()
            gain = delta.where(delta > 0, 0).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / loss.replace(0, 1e-10)
            rsi = 100 - (100 / (1 + rs))
            rsi_val = float(rsi.iloc[-1]) if not np.isnan(rsi.iloc[-1]) else 50.0
            
            macd_bullish = bool(macd_current > 0 and macd_prev <= 0)
            macd_bearish = bool(macd_current < 0 and macd_prev >= 0)
            
            signal = "HOLD"
            confidence = 0.3
            
            if macd_bullish and rsi_val < 65:
                signal = "BUY"
                confidence = min(0.5 + (65 - rsi_val) / 100, 0.85)
            elif macd_bearish and rsi_val > 35:
                signal = "SELL"
                confidence = min(0.5 + (rsi_val - 35) / 100, 0.85)
            elif rsi_val < 30:
                signal = "BUY"
                confidence = 0.65
            elif rsi_val > 70:
                signal = "SELL"
                confidence = 0.65
            
            kelly_fraction = 0.15 if confidence > 0.7 else 0.10 if confidence > 0.5 else 0.05
            
            return {
                "agent": self.name, "symbol": symbol, "signal": signal,
                "confidence": round(confidence, 2),
                "macd_histogram": round(macd_current, 6),
                "macd_crossover": "bullish" if macd_bullish else "bearish" if macd_bearish else "none",
                "rsi": round(rsi_val, 1),
                "kelly_fraction": kelly_fraction, "risk_tolerance": self.risk_tolerance,
                "reasoning": f"Tudor Jones: MACD={'bull' if macd_bullish else 'bear' if macd_bearish else 'flat'}, RSI={rsi_val:.0f}"
            }
        except Exception as e:
            return self._empty(symbol, str(e))
    
    def _empty(self, symbol, error):
        return {"agent": self.name, "symbol": symbol, "signal": "HOLD", "confidence": 0.3, "error": error}
