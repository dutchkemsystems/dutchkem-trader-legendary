"""Fair Value Gap (FVG) detection indicator.

FVGs represent price inefficiencies — gaps between candle 1 high and
candle 3 low (bullish) or candle 1 low and candle 3 high (bearish).
Price tends to return to fill these gaps.
"""

import pandas as pd
from typing import List, Dict


def find_fvgs(data: pd.DataFrame) -> List[Dict]:
    """Find Fair Value Gaps — 3-candle pattern with middle gap.
    
    Bullish FVG: candle1 high < candle3 low (gap up)
    Bearish FVG: candle1 low > candle3 high (gap down)
    
    Args:
        data: OHLCV DataFrame
        
    Returns:
        List of FVG dicts with type, top, bottom, index
    """
    fvgs = []
    
    if len(data) < 3:
        return fvgs
    
    for i in range(2, len(data)):
        candle1 = data.iloc[i - 2]
        candle3 = data.iloc[i]
        
        # Bullish FVG: gap between candle1 high and candle3 low
        if candle1['high'] < candle3['low']:
            fvgs.append({
                'type': 'bullish',
                'top': candle3['low'],
                'bottom': candle1['high'],
                'index': i
            })
        # Bearish FVG: gap between candle1 low and candle3 high
        elif candle1['low'] > candle3['high']:
            fvgs.append({
                'type': 'bearish',
                'top': candle1['low'],
                'bottom': candle3['high'],
                'index': i
            })
    
    return fvgs


def is_near_fvg(current_price: float, fvgs: List[Dict], max_distance_pips: float = 5.0, pip_value: float = 0.0001) -> bool:
    """Check if current price is within threshold of an FVG.
    
    Args:
        current_price: Current market price
        fvgs: List of FVG dicts
        max_distance_pips: Maximum distance in pips
        pip_value: Value of 1 pip (0.0001 for most pairs)
        
    Returns:
        True if price is near any FVG
    """
    for fvg in fvgs[-5:]:  # Check last 5 FVGs
        midpoint = (fvg['top'] + fvg['bottom']) / 2
        distance = abs(current_price - midpoint)
        if distance < max_distance_pips * pip_value:
            return True
    return False
