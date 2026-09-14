"""Chiaroscuro Scalp Model Strategy.

Uses daily range expansion, order blocks, and fair value gaps
during London/NY sessions. Named after the art technique of
strong contrasts — finding the "light" (institutional interest)
in the "dark" (noise).

Confluence factors:
1. Daily range expansion (price moving beyond 50% of ATR)
2. Order block present (institutional footprint)
3. Fair value gap nearby (inefficiency to fill)
4. Session timing (London or NY hours)
5. Momentum confirmation (RSI direction)
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
import pandas as pd
import numpy as np

from ..base import ScalpingStrategy
from ..signals import ScalpSignal, SignalDirection
from ..indicators.order_blocks import find_order_blocks
from ..indicators.fvg import find_fvgs, is_near_fvg


class ChiaroscuroStrategy(ScalpingStrategy):
    """Chiaroscuro Scalp Model — institutional confluence scalping."""
    
    def required_timeframes(self) -> List[str]:
        return ['M5', 'M15', 'H1']
    
    def analyze(self, symbol: str, data: Dict[str, pd.DataFrame]) -> Optional[ScalpSignal]:
        """Analyze market data for Chiaroscuro setup."""
        m5 = data.get('M5')
        m15 = data.get('M15')
        h1 = data.get('H1')
        
        if m5 is None or m15 is None or h1 is None:
            return None
        
        if len(m5) < 20 or len(m15) < 20 or len(h1) < 20:
            return None
        
        # 1. Check daily range expansion
        daily_range = self._calculate_daily_range(h1)
        if not daily_range['expanded']:
            return None
        
        # 2. Find order blocks
        order_blocks = find_order_blocks(m15)
        if not order_blocks:
            return None
        
        # 3. Find fair value gaps
        fvgs = find_fvgs(m5)
        
        # 4. Check session timing
        if not self._is_optimal_session():
            return None
        
        # 5. Momentum confirmation
        rsi = self._calculate_rsi(m5, 14)
        
        # Determine direction based on order block side
        latest_ob = order_blocks[-1]
        direction = SignalDirection.BUY if latest_ob['type'] == 'demand' else SignalDirection.SELL
        
        # Check if price is near FVG (confluence boost)
        near_fvg = is_near_fvg(m5.iloc[-1]['close'], fvgs)
        
        # Calculate confidence
        confidence = 0.5  # Base
        if near_fvg:
            confidence += 0.2
        if daily_range['expansion_pct'] > 0.7:
            confidence += 0.15
        if rsi > 60 and direction == SignalDirection.BUY:
            confidence += 0.1
        elif rsi < 40 and direction == SignalDirection.SELL:
            confidence += 0.1
        
        confidence = min(confidence, 1.0)
        
        # Only trade if confidence >= threshold
        if confidence < self.config.get('min_confidence', 0.6):
            return None
        
        return ScalpSignal(
            direction=direction,
            symbol=symbol,
            strategy_name='chiaroscuro',
            entry_price=m5.iloc[-1]['close'],
            sl_pips=self.config.get('sl_pips', 12),
            tp_pips=self.config.get('tp_pips', 20),
            confidence=confidence,
            reason=f"Order block + {'FVG confluence' if near_fvg else 'range expansion'}",
            metadata={
                'order_block': latest_ob,
                'near_fvg': near_fvg,
                'daily_range': daily_range,
                'rsi': float(rsi)
            }
        )
    
    def _calculate_daily_range(self, h1_data: pd.DataFrame) -> dict:
        """Check if daily range is expanding beyond 50% of ATR."""
        atr = h1_data['high'].rolling(14).max() - h1_data['low'].rolling(14).min()
        current_range = h1_data['high'].iloc[-1] - h1_data['low'].iloc[-1]
        atr_val = atr.iloc[-1] if not np.isnan(atr.iloc[-1]) else 0.001
        expansion_pct = current_range / atr_val if atr_val > 0 else 0
        
        return {
            'expanded': expansion_pct > 0.5,
            'expansion_pct': float(expansion_pct),
            'atr': float(atr_val)
        }
    
    def _calculate_rsi(self, data: pd.DataFrame, period: int = 14) -> float:
        """Calculate RSI."""
        delta = data['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        val = rsi.iloc[-1]
        return float(val) if not np.isnan(val) else 50.0
    
    def _is_optimal_session(self) -> bool:
        """Check if within London or NY session."""
        now = datetime.utcnow().hour
        # London: 07:00-16:00 UTC, NY: 12:00-21:00 UTC
        return (7 <= now <= 16) or (12 <= now <= 21)
