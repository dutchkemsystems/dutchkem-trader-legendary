"""Liquidity Sweep detection indicator.

Liquidity sweeps (stop hunts) occur when price temporarily breaks
beyond a key level (swing high/low, support/resistance) to trigger
stop losses, then reverses. This is a key Smart Money Concept.
"""

import pandas as pd
from typing import List, Dict, Optional


def find_liquidity_sweeps(data: pd.DataFrame, lookback: int = 20, sweep_buffer_pips: float = 2.0, pip_value: float = 0.0001) -> List[Dict]:
    """Detect liquidity sweep patterns.
    
    A liquidity sweep occurs when:
    1. Price breaks above a swing high (or below swing low)
    2. The break is temporary (wick, not full body close)
    3. Price reverses back below the level (or above for lows)
    
    Args:
        data: OHLCV DataFrame
        lookback: Number of bars to look for key levels
        sweep_buffer_pips: Minimum break distance in pips
        pip_value: Value of 1 pip
        
    Returns:
        List of sweep dicts with type, level, sweep_high, index
    """
    sweeps = []
    
    if len(data) < lookback + 3:
        return sweeps
    
    buffer = sweep_buffer_pips * pip_value
    
    # Find recent swing highs and lows as key levels
    from .bos import find_swing_points
    swings = find_swing_points(data, swing_length=3)
    
    swing_highs = [s for s in swings if s['type'] == 'swing_high']
    swing_lows = [s for s in swings if s['type'] == 'swing_low']
    
    # Check recent bars for sweep patterns
    for i in range(max(lookback, 10), len(data)):
        current = data.iloc[i]
        prev = data.iloc[i - 1]
        
        # Bullish sweep: wick below swing low, close above
        for sl in swing_lows:
            if sl['index'] < i - 1:
                level = sl['price']
                # Wick below level
                if current['low'] < level - buffer:
                    # Close above level (rejection)
                    if current['close'] > level:
                        # Previous bar was also above (confirming level)
                        if prev['close'] > level or prev['low'] > level - buffer:
                            sweeps.append({
                                'type': 'bullish_sweep',
                                'level': level,
                                'sweep_low': current['low'],
                                'close': current['close'],
                                'index': i,
                                'swing_index': sl['index']
                            })
        
        # Bearish sweep: wick above swing high, close below
        for sh in swing_highs:
            if sh['index'] < i - 1:
                level = sh['price']
                # Wick above level
                if current['high'] > level + buffer:
                    # Close below level (rejection)
                    if current['close'] < level:
                        # Previous bar was also below (confirming level)
                        if prev['close'] < level or prev['high'] < level + buffer:
                            sweeps.append({
                                'type': 'bearish_sweep',
                                'level': level,
                                'sweep_high': current['high'],
                                'close': current['close'],
                                'index': i,
                                'swing_index': sh['index']
                            })
    
    return sweeps


def get_latest_sweep(data: pd.DataFrame, lookback: int = 20) -> Optional[Dict]:
    """Get the most recent liquidity sweep.
    
    Args:
        data: OHLCV DataFrame
        lookback: Number of bars to scan
        
    Returns:
        Latest sweep dict or None
    """
    sweeps = find_liquidity_sweeps(data, lookback)
    if not sweeps:
        return None
    sweeps.sort(key=lambda x: x['index'], reverse=True)
    return sweeps[0]


def is_liquidity_sweep_active(data: pd.DataFrame, direction: str, lookback: int = 20) -> bool:
    """Check if there's a recent liquidity sweep in the given direction.
    
    Args:
        data: OHLCV DataFrame
        direction: 'BUY' or 'SELL'
        lookback: Number of bars to scan
        
    Returns:
        True if recent sweep matches direction
    """
    sweep = get_latest_sweep(data, lookback)
    if sweep is None:
        return False
    
    # Only consider sweeps in the last 5 bars
    if sweep['index'] < len(data) - 5:
        return False
    
    if direction == 'BUY' and sweep['type'] == 'bullish_sweep':
        return True
    if direction == 'SELL' and sweep['type'] == 'bearish_sweep':
        return True
    
    return False
