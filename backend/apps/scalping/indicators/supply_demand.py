"""Supply/Demand Zone detection indicator."""

import pandas as pd
from typing import List, Dict


def find_supply_demand_zones(data: pd.DataFrame, lookback: int = 20) -> List[Dict]:
    """Find supply and demand zones."""
    zones = []
    
    if len(data) < lookback + 2:
        return zones
    
    for i in range(len(data) - lookback, len(data) - 1):
        current = data.iloc[i]
        next_candle = data.iloc[i + 1]
        
        body = abs(next_candle['close'] - next_candle['open'])
        start_idx = max(0, i - 5)
        avg_body = abs(data['close'].iloc[start_idx:i] - data['open'].iloc[start_idx:i]).mean()
        
        if avg_body == 0:
            continue
            
        if body > 1.5 * avg_body:
            if next_candle['close'] > next_candle['open'] and current['close'] < current['open']:
                zones.append({'type': 'demand', 'high': current['high'], 'low': current['low'], 'index': i})
            elif next_candle['close'] < next_candle['open'] and current['close'] > current['open']:
                zones.append({'type': 'supply', 'high': current['high'], 'low': current['low'], 'index': i})
    
    return zones


def is_rejection_candle(candle: pd.Series, direction: str) -> bool:
    """Check if candle is a rejection candle (pin bar or engulfing)."""
    body = abs(candle['close'] - candle['open'])
    total_range = candle['high'] - candle['low']
    
    if total_range == 0:
        return False
    
    wick_ratio = body / total_range
    
    # Pin bar: small body, long wick
    if wick_ratio < 0.3:
        return True
    
    # Engulfing: body covers previous candle
    return False
