"""
Warren Buffett - Value Investing & Margin of Safety
"Price is what you pay, value is what you get."
"""
import pandas as pd
import numpy as np
from typing import Dict, Any

class BuffettAgent:
    def __init__(self):
        self.name = "Warren Buffett"
        self.philosophy = "Value Investing + Margin of Safety"
        self.specialties = ["value_fundamentals", "margin_of_safety", "long_term_trends"]
        self.risk_tolerance = 0.60
        self.max_position = 0.15

    def analyze(self, data: pd.DataFrame, symbol: str) -> Dict[str, Any]:
        try:
            close = data['close'].dropna()
            if len(close) < 50:
                return self._empty(symbol, "Insufficient data")
            
            ma50 = close.rolling(min(50, len(close))).mean().dropna()
            fair_value = float(ma50.iloc[-1])
            margin_of_safety = float((fair_value - close.iloc[-1]) / abs(fair_value) * 100) if abs(fair_value) > 0 else 0.0
            
            volatility = close.pct_change().rolling(20).std().dropna() * np.sqrt(252) * 100
            moat_score = float(max(0, 100 - volatility.iloc[-1])) if len(volatility) > 0 else 50.0
            
            signal = "HOLD"
            confidence = 0.3
            
            if margin_of_safety > 5:
                signal = "BUY"
                confidence = min(0.5 + margin_of_safety / 20, 0.85)
            elif margin_of_safety < -5:
                signal = "SELL"
                confidence = min(0.4 + abs(margin_of_safety) / 20, 0.75)
            elif moat_score > 70:
                signal = "BUY"
                confidence = 0.4 + moat_score / 500
            
            kelly_fraction = 0.15 if confidence > 0.7 else 0.10 if confidence > 0.5 else 0.05
            
            return {
                "agent": self.name, "symbol": symbol, "signal": signal,
                "confidence": round(confidence, 2),
                "fair_value": round(fair_value, 5),
                "margin_of_safety": round(margin_of_safety, 2),
                "moat_score": round(moat_score, 1),
                "kelly_fraction": kelly_fraction, "risk_tolerance": self.risk_tolerance,
                "reasoning": f"Buffett Value: MoS={margin_of_safety:.1f}%, Moat={moat_score:.0f}"
            }
        except Exception as e:
            return self._empty(symbol, str(e))
    
    def _empty(self, symbol, error):
        return {"agent": self.name, "symbol": symbol, "signal": "HOLD", "confidence": 0.3, "error": error}
