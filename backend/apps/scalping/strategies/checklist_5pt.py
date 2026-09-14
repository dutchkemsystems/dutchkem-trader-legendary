"""5-Point Checklist Strategy.

Only trade when 5 conditions align:
1. H1 impulse candle
2. Premium/discount zone
3. Point of Interest nearby
4. Liquidity sweep occurred
5. Within session window
"""

from typing import Optional, List, Dict
from datetime import datetime
import pandas as pd
import numpy as np

from ..base import ScalpingStrategy
from ..signals import ScalpSignal, SignalDirection


class FivePointChecklistStrategy(ScalpingStrategy):
    """5-Point Checklist — multi-factor confirmation scalping."""
    
    def required_timeframes(self) -> List[str]:
        return ['M5', 'H1']
    
    def analyze(self, symbol: str, data: Dict[str, pd.DataFrame]) -> Optional[ScalpSignal]:
        m5 = data.get('M5')
        h1 = data.get('H1')
        
        if m5 is None or h1 is None:
            return None
        
        if len(m5) < 20 or len(h1) < 20:
            return None
        
        conditions_met = 0
        
        # 1. H1 impulse candle
        last_h1 = h1.iloc[-1]
        h1_body = abs(last_h1['close'] - last_h1['open'])
        h1_range = last_h1['high'] - last_h1['low']
        if h1_range > 0 and h1_body / h1_range > 0.6:
            conditions_met += 1
        
        # 2. Premium/discount zone
        h1_high = h1['high'].rolling(20).max().iloc[-1]
        h1_low = h1['low'].rolling(20).min().iloc[-1]
        mid = (h1_high + h1_low) / 2
        current_price = m5.iloc[-1]['close']
        if current_price < mid:  # Discount zone
            conditions_met += 1
        
        # 3. Point of Interest (simplified: round number)
        if abs(current_price * 10000 % 50) < 5:
            conditions_met += 1
        
        # 4. Liquidity sweep (price moved beyond recent high/low then reversed)
        recent_high = m5['high'].rolling(10).max().iloc[-2]
        recent_low = m5['low'].rolling(10).min().iloc[-2]
        if m5.iloc[-1]['low'] < recent_low or m5.iloc[-1]['high'] > recent_high:
            conditions_met += 1
        
        # 5. Session window
        now = datetime.utcnow().hour
        if (7 <= now <= 16) or (12 <= now <= 21):
            conditions_met += 1
        
        min_conditions = self.config.get('min_conditions', 5)
        if conditions_met < min_conditions:
            return None
        
        # Determine direction
        direction = SignalDirection.BUY if current_price < mid else SignalDirection.SELL
        
        confidence = 0.5 + (conditions_met * 0.1)
        confidence = min(confidence, 1.0)
        
        return ScalpSignal(
            direction=direction,
            symbol=symbol,
            strategy_name='checklist_5point',
            entry_price=current_price,
            sl_pips=self.config.get('sl_pips', 10),
            tp_pips=self.config.get('tp_pips', 15),
            confidence=confidence,
            reason=f"{conditions_met}/5 conditions met",
            metadata={'conditions_met': conditions_met}
        )
