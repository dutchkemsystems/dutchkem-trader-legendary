"""London/NY Overlap Scalping Strategy.

Trade the highest liquidity window (13:00-17:00 GMT).
Tight spreads, high volatility. Enter on Bollinger Band squeeze
breakout with volume confirmation.
"""

from typing import Optional, List, Dict
from datetime import datetime
import pandas as pd
import numpy as np

from ..base import ScalpingStrategy
from ..signals import ScalpSignal, SignalDirection


class LondonNYOverlapStrategy(ScalpingStrategy):
    """London/NY Overlap — highest liquidity window scalping."""
    
    def required_timeframes(self) -> List[str]:
        return ['M1', 'M5']
    
    def analyze(self, symbol: str, data: Dict[str, pd.DataFrame]) -> Optional[ScalpSignal]:
        """Analyze for London/NY overlap breakout."""
        m1 = data.get('M1')
        m5 = data.get('M5')
        
        if m1 is None or m5 is None:
            return None
        
        if len(m1) < 20 or len(m5) < 20:
            return None
        
        # Check if we're in the overlap window (13:00-17:00 UTC)
        if not self._is_overlap_session():
            return None
        
        # Calculate Bollinger Bands on M5
        bb = self._calculate_bollinger_bands(m5, 20, 2)
        if bb is None:
            return None
        
        # Check for BB squeeze (narrow bands)
        bb_width = (bb['upper'] - bb['lower']) / bb['middle']
        squeeze_threshold = self.config.get('bb_squeeze_threshold', 0.02)
        
        if bb_width > squeeze_threshold:
            return None  # Bands not tight enough
        
        # Check for breakout on M1
        last_m1 = m1.iloc[-1]
        prev_m1 = m1.iloc[-2]
        
        # Volume confirmation
        avg_volume = m1['volume'].rolling(20).mean().iloc[-1]
        volume_spike = last_m1['volume'] > avg_volume * 1.5
        
        if not volume_spike:
            return None
        
        # Determine direction based on breakout
        if last_m1['close'] > bb['upper']:
            direction = SignalDirection.BUY
        elif last_m1['close'] < bb['lower']:
            direction = SignalDirection.SELL
        else:
            return None
        
        # Calculate confidence
        confidence = 0.5
        if volume_spike:
            confidence += 0.2
        if bb_width < squeeze_threshold / 2:
            confidence += 0.15  # Very tight squeeze
        
        confidence = min(confidence, 1.0)
        
        return ScalpSignal(
            direction=direction,
            symbol=symbol,
            strategy_name='london_ny_overlap',
            entry_price=last_m1['close'],
            sl_pips=self.config.get('sl_pips', 10),
            tp_pips=self.config.get('tp_pips', 15),
            confidence=confidence,
            reason=f"BB squeeze breakout + volume spike",
            metadata={
                'bb_width': float(bb_width),
                'volume_ratio': float(last_m1['volume'] / avg_volume) if avg_volume > 0 else 1.0,
            }
        )
    
    def _calculate_bollinger_bands(self, data: pd.DataFrame, period: int = 20, std_dev: float = 2) -> Optional[Dict]:
        """Calculate Bollinger Bands."""
        if len(data) < period:
            return None
        
        middle = data['close'].rolling(period).mean()
        std = data['close'].rolling(period).std()
        
        return {
            'upper': middle + std_dev * std,
            'lower': middle - std_dev * std,
            'middle': middle
        }
    
    def _is_overlap_session(self) -> bool:
        """Check if current time is within London/NY overlap (13:00-17:00 UTC)."""
        now = datetime.utcnow().hour
        return 13 <= now <= 17
