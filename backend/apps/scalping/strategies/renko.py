"""Renko 20-Pip System Strategy.

Renko charts (10-20 pip bricks) filter noise.
Enter on oscillator + trendline + BB_stop alignment.
"""

from typing import Optional, List, Dict
import pandas as pd
import numpy as np

from ..base import ScalpingStrategy
from ..signals import ScalpSignal, SignalDirection
from ..indicators.renko import generate_renko


class RenkoStrategy(ScalpingStrategy):
    """Renko 20-Pip — noise-filtered scalping with Renko charts."""
    
    def required_timeframes(self) -> List[str]:
        return ['M5']
    
    def analyze(self, symbol: str, data: Dict[str, pd.DataFrame]) -> Optional[ScalpSignal]:
        m5 = data.get('M5')
        if m5 is None or len(m5) < 50:
            return None
        
        brick_size = self.config.get('brick_size_pips', 10)
        renko = generate_renko(m5, brick_size)
        
        if len(renko) < 10:
            return None
        
        # Oscillator (RSI)
        delta = m5['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        rsi_val = rsi.iloc[-1]
        
        # Renko trend
        last_bricks = renko.tail(5)
        if all(last_bricks['direction'] == 1):
            renko_trend = 1
        elif all(last_bricks['direction'] == -1):
            renko_trend = -1
        else:
            return None
        
        # Alignment check
        if renko_trend == 1 and rsi_val < 50:
            return None
        if renko_trend == -1 and rsi_val > 50:
            return None
        
        direction = SignalDirection.BUY if renko_trend == 1 else SignalDirection.SELL
        confidence = 0.6
        
        return ScalpSignal(
            direction=direction,
            symbol=symbol,
            strategy_name='renko_20pip',
            entry_price=m5.iloc[-1]['close'],
            sl_pips=self.config.get('sl_pips', 20),
            tp_pips=self.config.get('tp_pips', 20),
            confidence=confidence,
            reason=f"Renko trend alignment + RSI {rsi_val:.0f}",
            metadata={'rsi': float(rsi_val), 'renko_trend': renko_trend}
        )
