"""10/20 EMA Pullback Strategy.

10 EMA crosses 20 EMA. Enter on pullback to 20 EMA with confirmation candle.
"""

from typing import Optional, List, Dict
import pandas as pd
import numpy as np

from ..base import ScalpingStrategy
from ..signals import ScalpSignal, SignalDirection


class EMAPullbackStrategy(ScalpingStrategy):
    """EMA Pullback — trend-following with pullback entries."""
    
    def required_timeframes(self) -> List[str]:
        return ['M5']
    
    def analyze(self, symbol: str, data: Dict[str, pd.DataFrame]) -> Optional[ScalpSignal]:
        m5 = data.get('M5')
        if m5 is None or len(m5) < 30:
            return None
        
        ema_fast = self.config.get('ema_fast', 10)
        ema_slow = self.config.get('ema_slow', 20)
        
        ema_f = m5['close'].ewm(span=ema_fast).mean()
        ema_s = m5['close'].ewm(span=ema_slow).mean()
        
        # Check for crossover in last 5 candles
        for i in range(-5, -1):
            if ema_f.iloc[i] > ema_s.iloc[i] and ema_f.iloc[i-1] <= ema_s.iloc[i-1]:
                crossover_bull = True
                break
            elif ema_f.iloc[i] < ema_s.iloc[i] and ema_f.iloc[i-1] >= ema_s.iloc[i-1]:
                crossover_bull = False
                break
        else:
            return None
        
        # Check for pullback to slow EMA
        last_close = m5.iloc[-1]['close']
        ema_slow_val = ema_s.iloc[-1]
        
        pullback_threshold = 0.0005
        if abs(last_close - ema_slow_val) > pullback_threshold:
            return None
        
        # Confirmation candle
        last = m5.iloc[-1]
        if crossover_bull and last['close'] > last['open']:
            direction = SignalDirection.BUY
        elif not crossover_bull and last['close'] < last['open']:
            direction = SignalDirection.SELL
        else:
            return None
        
        confidence = 0.65
        
        return ScalpSignal(
            direction=direction,
            symbol=symbol,
            strategy_name='ema_pullback',
            entry_price=last_close,
            sl_pips=self.config.get('sl_pips', 12),
            tp_pips=self.config.get('tp_pips', 20),
            confidence=confidence,
            reason="EMA pullback with confirmation",
            metadata={'ema_fast': float(ema_f.iloc[-1]), 'ema_slow': float(ema_slow_val)}
        )
