"""
George Soros - Reflexivity & Macro Trend Following
"The market is always wrong, but eventually corrects itself."
"""
import pandas as pd
import numpy as np
from typing import Dict, Any

def _p(v):
    """Convert numpy/pandas types to native Python for JSON serialization."""
    if isinstance(v, (np.floating, np.integer)):
        return float(v)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    return v

class SorosAgent:
    def __init__(self):
        self.name = "George Soros"
        self.philosophy = "Reflexivity Theory"
        self.specialties = ["macro_trends", "reflexivity", "asymmetric_bets"]
        self.risk_tolerance = 0.85
        self.max_position = 0.25

    def analyze(self, data: pd.DataFrame, symbol: str) -> Dict[str, Any]:
        try:
            close = data['close'].dropna()
            high = data['high'].dropna()
            low = data['low'].dropna()
            
            if len(close) < 50:
                return self._empty(symbol, "Insufficient data")
            
            ema20 = close.ewm(span=20).mean()
            ema50 = close.ewm(span=min(50, len(close)-1)).mean()
            
            slope_20 = float((ema20.iloc[-1] - ema20.iloc[-20]) / abs(ema20.iloc[-20]) * 100) if abs(ema20.iloc[-20]) > 0 else 0.0
            slope_50 = float((ema50.iloc[-1] - ema50.iloc[-min(50, len(ema50)-1)]) / abs(ema50.iloc[-min(50, len(ema50)-1)]) * 100) if len(ema50) > 5 else 0.0
            
            reflexivity_score = 0.0
            if slope_20 > 0 and slope_50 > 0:
                reflexivity_score = min(abs(slope_20) + abs(slope_50), 100.0)
            elif slope_20 < 0 and slope_50 < 0:
                reflexivity_score = min(abs(slope_20) + abs(slope_50), 100.0)
            
            atr = (high - low).rolling(14).mean().dropna()
            atr_ratio = float(atr.iloc[-1] / atr.iloc[-min(50, len(atr))]) if len(atr) > 1 and atr.iloc[-min(50, len(atr))] > 0 else 1.0
            volatility_squeeze = bool(atr_ratio < 0.7)
            
            equilibrium = float((ema20.iloc[-1] + ema50.iloc[-1]) / 2)
            deviation = float((close.iloc[-1] - equilibrium) / abs(equilibrium) * 100) if abs(equilibrium) > 0 else 0.0
            
            signal = "HOLD"
            confidence = 0.3
            
            if reflexivity_score > 50 and volatility_squeeze:
                signal = "BUY" if slope_20 > 0 else "SELL"
                confidence = min(0.5 + reflexivity_score / 200, 0.9)
            elif abs(deviation) > 3:
                signal = "SELL" if deviation > 0 else "BUY"
                confidence = min(0.4 + abs(deviation) / 10, 0.8)
            elif reflexivity_score > 30:
                signal = "BUY" if slope_20 > 0 else "SELL"
                confidence = min(0.4 + reflexivity_score / 200, 0.8)
            
            kelly_fraction = 0.25 if confidence > 0.7 else 0.15 if confidence > 0.5 else 0.10
            
            return {
                "agent": self.name, "symbol": symbol, "signal": signal,
                "confidence": round(confidence, 2),
                "reflexivity_score": round(reflexivity_score, 1),
                "slope_20": round(slope_20, 4), "slope_50": round(slope_50, 4),
                "volatility_squeeze": volatility_squeeze,
                "price_deviation": round(deviation, 2),
                "equilibrium": round(equilibrium, 5),
                "kelly_fraction": kelly_fraction, "risk_tolerance": self.risk_tolerance,
                "reasoning": f"Soros Reflexivity: Score={reflexivity_score:.0f}, Squeeze={volatility_squeeze}, Dev={deviation:.1f}%"
            }
        except Exception as e:
            return self._empty(symbol, str(e))
    
    def _empty(self, symbol, error):
        return {"agent": self.name, "symbol": symbol, "signal": "HOLD", "confidence": 0.3, "error": error}
