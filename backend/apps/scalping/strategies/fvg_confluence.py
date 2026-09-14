"""Multi-Timeframe FVG Confluence Strategy.

H4 Fair Value Gaps as reference, enter on M5 when price returns
to FVG with confirmation.
"""

from typing import Optional, List, Dict
import pandas as pd
import numpy as np

from ..base import ScalpingStrategy
from ..signals import ScalpSignal, SignalDirection
from ..indicators.fvg import find_fvgs, is_near_fvg


class FVGConfluenceStrategy(ScalpingStrategy):
    """FVG Confluence — multi-timeframe institutional reference scalping."""
    
    def required_timeframes(self) -> List[str]:
        return ['M5', 'H4']
    
    def analyze(self, symbol: str, data: Dict[str, pd.DataFrame]) -> Optional[ScalpSignal]:
        m5 = data.get('M5')
        h4 = data.get('H4')
        
        if m5 is None or h4 is None:
            return None
        
        if len(m5) < 20 or len(h4) < 20:
            return None
        
        # Find H4 FVGs
        h4_fvgs = find_fvgs(h4)
        if not h4_fvgs:
            return None
        
        # Check if M5 price is near any H4 FVG
        last_close = m5.iloc[-1]['close']
        near_fvg = None
        
        for fvg in h4_fvgs[-3:]:
            midpoint = (fvg['top'] + fvg['bottom']) / 2
            distance = abs(last_close - midpoint)
            if distance < 0.0020:  # Within 20 pips
                near_fvg = fvg
                break
        
        if near_fvg is None:
            return None
        
        # M5 confirmation candle
        last = m5.iloc[-1]
        if near_fvg['type'] == 'bullish' and last['close'] > last['open']:
            direction = SignalDirection.BUY
        elif near_fvg['type'] == 'bearish' and last['close'] < last['open']:
            direction = SignalDirection.SELL
        else:
            return None
        
        confidence = 0.65
        
        return ScalpSignal(
            direction=direction,
            symbol=symbol,
            strategy_name='fvg_confluence',
            entry_price=last_close,
            sl_pips=self.config.get('sl_pips', 10),
            tp_pips=self.config.get('tp_pips', 15),
            confidence=confidence,
            reason=f"H4 FVG {near_fvg['type']} confluence",
            metadata={'h4_fvg': near_fvg}
        )
