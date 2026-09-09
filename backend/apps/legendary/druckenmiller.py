"""
Stanley Druckenmiller - Concentration & Asymmetric Bets
"It's not whether you're right or wrong that's important, but how much money you make when you're right."
"""
import pandas as pd
import numpy as np
from typing import Dict, Any

class DruckenmillerAgent:
    def __init__(self):
        self.name = "Stanley Druckenmiller"
        self.philosophy = "Concentration + Asymmetric Risk-Reward"
        self.specialties = ["asymmetric_bets", "momentum", "concentration"]
        self.risk_tolerance = 0.80
        self.max_position = 0.20

    def analyze(self, data: pd.DataFrame, symbol: str) -> Dict[str, Any]:
        try:
            close = data['close'].dropna()
            high = data['high'].dropna()
            low = data['low'].dropna()
            
            if len(close) < 21:
                return self._empty(symbol, "Insufficient data")
            
            roc_5 = float((close.iloc[-1] / close.iloc[-6] - 1) * 100) if close.iloc[-6] != 0 else 0.0
            roc_20 = float((close.iloc[-1] / close.iloc[-21] - 1) * 100) if len(close) >= 21 and close.iloc[-21] != 0 else 0.0
            
            high_20 = high.rolling(20).max().dropna()
            low_20 = low.rolling(20).min().dropna()
            range_pos = float((close.iloc[-1] - low_20.iloc[-1]) / (high_20.iloc[-1] - low_20.iloc[-1]) * 100) if (high_20.iloc[-1] - low_20.iloc[-1]) > 0 else 50.0
            
            upside = float((high_20.iloc[-1] - close.iloc[-1]) / close.iloc[-1] * 100) if close.iloc[-1] > 0 else 0.0
            downside = float((close.iloc[-1] - low_20.iloc[-1]) / close.iloc[-1] * 100) if close.iloc[-1] > 0 else 0.0
            risk_reward = upside / downside if downside > 0.01 else 0.0
            
            signal = "HOLD"
            confidence = 0.3
            
            if risk_reward > 2.0 and roc_5 > 0:
                signal = "BUY"
                confidence = min(0.5 + risk_reward / 5, 0.9)
            elif risk_reward < 0.5 and roc_5 < 0:
                signal = "SELL"
                confidence = min(0.5 + min(1/(risk_reward+0.01), 2) / 5, 0.85)
            elif range_pos > 80 and roc_20 > 2:
                signal = "BUY"
                confidence = 0.6
            elif range_pos < 20 and roc_20 < -2:
                signal = "SELL"
                confidence = 0.6
            
            kelly_fraction = 0.20 if confidence > 0.7 else 0.12 if confidence > 0.5 else 0.08
            
            return {
                "agent": self.name, "symbol": symbol, "signal": signal,
                "confidence": round(confidence, 2),
                "roc_5": round(roc_5, 2), "roc_20": round(roc_20, 2),
                "range_position": round(range_pos, 1),
                "risk_reward": round(risk_reward, 2),
                "kelly_fraction": kelly_fraction, "risk_tolerance": self.risk_tolerance,
                "reasoning": f"Druckenmiller Asymmetric: RR={risk_reward:.2f}, ROC5={roc_5:.1f}%, Range={range_pos:.0f}%"
            }
        except Exception as e:
            return self._empty(symbol, str(e))
    
    def _empty(self, symbol, error):
        return {"agent": self.name, "symbol": symbol, "signal": "HOLD", "confidence": 0.3, "error": error}
