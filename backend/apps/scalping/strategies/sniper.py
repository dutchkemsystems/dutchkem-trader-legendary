"""Sniper Strategy.

Supply/demand zones + price action rejection candles.
Enter at institutional levels.
"""

from typing import Optional, List, Dict
import pandas as pd
import numpy as np

from ..base import ScalpingStrategy
from ..signals import ScalpSignal, SignalDirection
from ..indicators.supply_demand import find_supply_demand_zones, is_rejection_candle


class SniperStrategy(ScalpingStrategy):
    """Sniper — institutional level scalping with rejection candles."""
    
    def required_timeframes(self) -> List[str]:
        return ['M1', 'M5']
    
    def analyze(self, symbol: str, data: Dict[str, pd.DataFrame]) -> Optional[ScalpSignal]:
        m1 = data.get('M1')
        m5 = data.get('M5')
        
        if m1 is None or m5 is None:
            return None
        
        if len(m1) < 20 or len(m5) < 20:
            return None
        
        # Find supply/demand zones on M5
        zones = find_supply_demand_zones(m5)
        if not zones:
            return None
        
        # Check if price is near a zone
        last_m1 = m1.iloc[-1]
        near_zone = None
        
        for zone in zones[-3:]:
            if zone['low'] <= last_m1['close'] <= zone['high']:
                near_zone = zone
                break
        
        if near_zone is None:
            return None
        
        # Check for rejection candle on M1
        if self.config.get('require_rejection_candle', True):
            if not is_rejection_candle(last_m1, near_zone['type']):
                return None
        
        # Determine direction
        if near_zone['type'] == 'demand':
            direction = SignalDirection.BUY
        else:
            direction = SignalDirection.SELL
        
        # Calculate confidence
        confidence = 0.6
        if is_rejection_candle(last_m1, near_zone['type']):
            confidence += 0.2
        
        confidence = min(confidence, 1.0)
        
        return ScalpSignal(
            direction=direction,
            symbol=symbol,
            strategy_name='sniper',
            entry_price=last_m1['close'],
            sl_pips=self.config.get('sl_pips', 10),
            tp_pips=self.config.get('tp_pips', 15),
            confidence=confidence,
            reason=f"Rejection at {near_zone['type']} zone",
            metadata={'zone': near_zone}
        )
