"""
Peter Lynch - Growth at Reasonable Price (GARP)
"Invest in what you know."
"""
import pandas as pd
import numpy as np
from typing import Dict, Any

class LynchAgent:
    def __init__(self):
        self.name = "Peter Lynch"
        self.philosophy = "Growth at Reasonable Price (GARP)"
        self.specialties = ["growth_at_reasonable_price", "momentum_growth", "trend_participation"]
        self.risk_tolerance = 0.65
        self.max_position = 0.12

    def analyze(self, data: pd.DataFrame, symbol: str) -> Dict[str, Any]:
        try:
            close = data['close'].dropna()
            
            if len(close) < 31:
                return self._empty(symbol, "Insufficient data")
            
            roc_10 = float((close.iloc[-1] / close.iloc[-11] - 1) * 100) if close.iloc[-11] != 0 else 0.0
            roc_30 = float((close.iloc[-1] / close.iloc[-31] - 1) * 100) if len(close) >= 31 and close.iloc[-31] != 0 else 0.0
            
            growth_consistency = sum(1 for r in [roc_10, roc_30] if r > 0)
            
            ma20 = close.rolling(min(20, len(close))).mean().dropna()
            ma50 = close.rolling(min(50, len(close))).mean().dropna()
            
            price_to_ma50 = float(close.iloc[-1] / ma50.iloc[-1]) if len(ma50) > 0 and ma50.iloc[-1] != 0 else 1.0
            reasonable_price = bool(abs(price_to_ma50 - 1) < 0.05)
            
            signal = "HOLD"
            confidence = 0.3
            
            if roc_30 > 2 and reasonable_price and growth_consistency >= 1:
                signal = "BUY"
                confidence = min(0.5 + roc_30 / 10, 0.8)
            elif roc_30 < -2 and not reasonable_price:
                signal = "SELL"
                confidence = min(0.5 + abs(roc_30) / 10, 0.75)
            elif growth_consistency >= 2:
                signal = "BUY"
                confidence = 0.6
            elif growth_consistency == 0:
                signal = "SELL"
                confidence = 0.5
            
            kelly_fraction = 0.12 if confidence > 0.7 else 0.08 if confidence > 0.5 else 0.05
            
            return {
                "agent": self.name, "symbol": symbol, "signal": signal,
                "confidence": round(confidence, 2),
                "roc_10": round(roc_10, 2), "roc_30": round(roc_30, 2),
                "growth_consistency": growth_consistency,
                "price_to_ma50": round(price_to_ma50, 3),
                "reasonable_price": reasonable_price,
                "kelly_fraction": kelly_fraction, "risk_tolerance": self.risk_tolerance,
                "reasoning": f"Lynch GARP: Growth={growth_consistency}/2 periods, Price={'reasonable' if reasonable_price else 'expensive'}, ROC30={roc_30:.1f}%"
            }
        except Exception as e:
            return self._empty(symbol, str(e))
    
    def _empty(self, symbol, error):
        return {"agent": self.name, "symbol": symbol, "signal": "HOLD", "confidence": 0.3, "error": error}
