"""News Spike Fade Strategy.

After high-impact news (NFP, CPI, FOMC), wait for spike exhaustion,
enter on pullback.
"""

from typing import Optional, List, Dict
from datetime import datetime
import pandas as pd
import numpy as np

from ..base import ScalpingStrategy
from ..signals import ScalpSignal, SignalDirection


class NewsFadeStrategy(ScalpingStrategy):
    """News Fade — fade the spike after high-impact news."""
    
    def required_timeframes(self) -> List[str]:
        return ['M1', 'M5']
    
    def analyze(self, symbol: str, data: Dict[str, pd.DataFrame]) -> Optional[ScalpSignal]:
        m1 = data.get('M1')
        if m1 is None or len(m1) < 30:
            return None
        
        # Check for recent spike (last 10 candles)
        recent = m1.tail(10)
        price_change = abs(recent.iloc[-1]['close'] - recent.iloc[0]['open'])
        
        if price_change < 0.0010:  # Need at least 10 pip move
            return None
        
        # Wait period
        wait_minutes = self.config.get('wait_minutes', 5)
        if len(m1) < wait_minutes + 10:
            return None
        
        # RSI for exhaustion
        delta = m1['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        rsi_val = rsi.iloc[-1]
        
        # Fade direction (counter-trend)
        if recent.iloc[-1]['close'] > recent.iloc[0]['open']:
            # Price spiked up, fade short
            if rsi_val < 70:
                return None
            direction = SignalDirection.SELL
        else:
            # Price spiked down, fade long
            if rsi_val > 30:
                return None
            direction = SignalDirection.BUY
        
        confidence = 0.55
        
        return ScalpSignal(
            direction=direction,
            symbol=symbol,
            strategy_name='news_fade',
            entry_price=m1.iloc[-1]['close'],
            sl_pips=self.config.get('sl_pips', 8),
            tp_pips=self.config.get('tp_pips', 12),
            confidence=confidence,
            reason=f"News spike fade, RSI {rsi_val:.0f}",
            metadata={'rsi': float(rsi_val), 'spike_size': float(price_change)}
        )
