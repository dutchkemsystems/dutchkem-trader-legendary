"""Break of Structure (BoS) detection indicator.

BoS occurs when price breaks a previous swing high (bullish) or
swing low (bearish), confirming a trend continuation or reversal.
Used in Smart Money Concepts (SMC) trading.
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Optional


def find_swing_points(data: pd.DataFrame, swing_length: int = 5) -> List[Dict]:
    """Identify swing highs and swing lows.
    
    A swing high is a bar whose high is higher than the N bars on each side.
    A swing low is a bar whose low is lower than the N bars on each side.
    
    Args:
        data: OHLCV DataFrame
        swing_length: Number of bars on each side to confirm swing
        
    Returns:
        List of swing point dicts with type, price, index
    """
    swings = []
    
    if len(data) < swing_length * 2 + 1:
        return swings
    
    highs = data['high'].values
    lows = data['low'].values
    
    for i in range(swing_length, len(data) - swing_length):
        # Swing High: high is highest in the window
        is_swing_high = True
        for j in range(1, swing_length + 1):
            if highs[i] <= highs[i - j] or highs[i] <= highs[i + j]:
                is_swing_high = False
                break
        
        if is_swing_high:
            swings.append({
                'type': 'swing_high',
                'price': highs[i],
                'index': i
            })
        
        # Swing Low: low is lowest in the window
        is_swing_low = True
        for j in range(1, swing_length + 1):
            if lows[i] >= lows[i - j] or lows[i] >= lows[i + j]:
                is_swing_low = False
                break
        
        if is_swing_low:
            swings.append({
                'type': 'swing_low',
                'price': lows[i],
                'index': i
            })
    
    return swings


def detect_bos(data: pd.DataFrame, swing_length: int = 5) -> List[Dict]:
    """Detect Break of Structure events.
    
    Bullish BoS: Price breaks above a previous swing high
    Bearish BoS: Price breaks below a previous swing low
    
    Args:
        data: OHLCV DataFrame
        swing_length: Number of bars for swing detection
        
    Returns:
        List of BoS dicts with type, broken_level, break_index, strength
    """
    bos_events = []
    swings = find_swing_points(data, swing_length)
    
    if len(swings) < 2:
        return bos_events
    
    # Separate swing highs and lows
    swing_highs = [s for s in swings if s['type'] == 'swing_high']
    swing_lows = [s for s in swings if s['type'] == 'swing_low']
    
    # Check for breaks after each swing
    for i in range(len(data) - 1, max(swing_length, 10), -1):
        current_close = data['close'].iloc[i]
        
        # Check bullish BoS: close above most recent swing high
        for sh in reversed(swing_highs):
            if sh['index'] < i and current_close > sh['price']:
                # Verify it's a fresh break (not already broken)
                already_broken = any(
                    b['type'] == 'bullish' and b['broken_level'] == sh['price']
                    for b in bos_events
                )
                if not already_broken:
                    # Strength = how far above the swing high
                    strength = (current_close - sh['price']) / sh['price']
                    bos_events.append({
                        'type': 'bullish',
                        'broken_level': sh['price'],
                        'break_index': i,
                        'swing_index': sh['index'],
                        'strength': round(strength, 6)
                    })
                break
        
        # Check bearish BoS: close below most recent swing low
        for sl in reversed(swing_lows):
            if sl['index'] < i and current_close < sl['price']:
                already_broken = any(
                    b['type'] == 'bearish' and b['broken_level'] == sl['price']
                    for b in bos_events
                )
                if not already_broken:
                    strength = (sl['price'] - current_close) / sl['price']
                    bos_events.append({
                        'type': 'bearish',
                        'broken_level': sl['price'],
                        'break_index': i,
                        'swing_index': sl['index'],
                        'strength': round(strength, 6)
                    })
                break
    
    return bos_events


def get_latest_bos(data: pd.DataFrame, swing_length: int = 5) -> Optional[Dict]:
    """Get the most recent BoS event.
    
    Args:
        data: OHLCV DataFrame
        swing_length: Number of bars for swing detection
        
    Returns:
        Latest BoS dict or None
    """
    bos_events = detect_bos(data, swing_length)
    if not bos_events:
        return None
    # Sort by break_index descending (most recent first)
    bos_events.sort(key=lambda x: x['break_index'], reverse=True)
    return bos_events[0]
