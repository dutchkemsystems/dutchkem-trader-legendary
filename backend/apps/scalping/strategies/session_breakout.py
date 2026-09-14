"""Session Open Breakout Strategy.

Trade first 30-60 min of London (08:00 GMT) or NY (13:00 GMT).
Breakout of Asian range with volume confirmation.
"""

from typing import Optional, List, Dict
from datetime import datetime
import pandas as pd
import numpy as np

from ..base import ScalpingStrategy
from ..signals import ScalpSignal, SignalDirection


class SessionBreakoutStrategy(ScalpingStrategy):
    """Session Open Breakout — trade range breakouts at session opens."""
    
    def required_timeframes(self) -> List[str]:
        return ['M5', 'M15']
    
    def analyze(self, symbol: str, data: Dict[str, pd.DataFrame]) -> Optional[ScalpSignal]:
        """Analyze for session open breakout."""
        m5 = data.get('M5')
        m15 = data.get('M15')
        
        if m5 is None or m15 is None:
            return None
        
        if len(m5) < 60 or len(m15) < 20:
            return None
        
        # Check if we're in the breakout window
        session_info = self._get_session_info()
        if session_info is None:
            return None
        
        # Calculate Asian range (previous session's high/low)
        asian_range = self._calculate_asian_range(m15)
        if asian_range is None:
            return None
        
        # Check for breakout
        last_candle = m5.iloc[-1]
        breakout = self._check_breakout(last_candle, asian_range)
        
        if breakout is None:
            return None
        
        # Volume confirmation
        avg_volume = m5['volume'].rolling(20).mean().iloc[-1]
        volume_spike = last_candle['volume'] > avg_volume * 1.3
        
        if not volume_spike:
            return None
        
        # Calculate confidence
        confidence = 0.5
        if volume_spike:
            confidence += 0.15
        if breakout['breakout_strength'] > 0.001:
            confidence += 0.15
        
        confidence = min(confidence, 1.0)
        
        return ScalpSignal(
            direction=breakout['direction'],
            symbol=symbol,
            strategy_name='session_breakout',
            entry_price=last_candle['close'],
            sl_pips=self.config.get('sl_pips', 10),
            tp_pips=self.config.get('tp_pips', 15),
            confidence=confidence,
            reason=f"{session_info['name']} open breakout of Asian range",
            metadata={
                'session': session_info['name'],
                'asian_high': asian_range['high'],
                'asian_low': asian_range['low'],
                'breakout_strength': breakout['breakout_strength'],
            }
        )
    
    def _get_session_info(self) -> Optional[Dict]:
        """Check if current time is at session open."""
        now = datetime.utcnow()
        hour = now.hour
        minute = now.minute
        
        # London open: 08:00-09:00 UTC
        if hour == 8 and minute <= 60:
            return {'name': 'London', 'start_hour': 8}
        # NY open: 13:00-14:00 UTC
        elif hour == 13 and minute <= 60:
            return {'name': 'NY', 'start_hour': 13}
        
        return None
    
    def _calculate_asian_range(self, m15_data: pd.DataFrame) -> Optional[Dict]:
        """Calculate Asian session range (00:00-08:00 UTC)."""
        # Get last 24 hours of data
        recent = m15_data.tail(96)  # 24 hours * 4 candles/hour
        
        if len(recent) < 10:
            return None
        
        # Find candles in Asian session (00:00-08:00)
        asian_candles = []
        for idx, row in recent.iterrows():
            if hasattr(idx, 'hour'):
                if 0 <= idx.hour < 8:
                    asian_candles.append(row)
        
        if len(asian_candles) < 5:
            return None
        
        highs = [c['high'] for c in asian_candles]
        lows = [c['low'] for c in asian_candles]
        
        return {
            'high': max(highs),
            'low': min(lows)
        }
    
    def _check_breakout(self, candle: pd.Series, asian_range: Dict) -> Optional[Dict]:
        """Check if candle breaks out of Asian range."""
        range_size = asian_range['high'] - asian_range['low']
        
        # Breakout above Asian high
        if candle['close'] > asian_range['high']:
            return {
                'direction': SignalDirection.BUY,
                'breakout_strength': candle['close'] - asian_range['high']
            }
        # Breakdown below Asian low
        elif candle['close'] < asian_range['low']:
            return {
                'direction': SignalDirection.SELL,
                'breakout_strength': asian_range['low'] - candle['close']
            }
        
        return None
