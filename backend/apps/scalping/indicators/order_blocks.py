"""Order Block detection indicator.

Order blocks are institutional footprints — the last opposing candle
before a strong directional move. They represent areas where
institutional orders were likely placed.
"""

import pandas as pd
from typing import List, Dict


def find_order_blocks(data: pd.DataFrame, lookback: int = 20) -> List[Dict]:
    """Identify order blocks — last opposing candle before a strong move.
    
    Bullish OB: Last bearish candle before bullish impulse
    Bearish OB: Last bullish candle before bearish impulse
    
    Args:
        data: OHLCV DataFrame
        lookback: Number of bars to look back
        
    Returns:
        List of order block dicts with type, high, low, index
    """
    order_blocks = []
    
    if len(data) < lookback + 2:
        return order_blocks
    
    for i in range(len(data) - lookback, len(data) - 1):
        current = data.iloc[i]
        next_candle = data.iloc[i + 1]
        
        # Calculate candle bodies
        body = abs(next_candle['close'] - next_candle['open'])
        
        # Average body size for comparison
        start_idx = max(0, i - 5)
        avg_body = abs(data['close'].iloc[start_idx:i] - data['open'].iloc[start_idx:i]).mean()
        
        if avg_body == 0:
            continue
            
        # Strong move = body > 1.5x average
        if body > 1.5 * avg_body:
            # Bullish impulse
            if next_candle['close'] > next_candle['open']:
                # Current candle must be bearish (opposing)
                if current['close'] < current['open']:
                    order_blocks.append({
                        'type': 'demand',
                        'high': current['high'],
                        'low': current['low'],
                        'index': i
                    })
            # Bearish impulse
            elif next_candle['close'] < next_candle['open']:
                # Current candle must be bullish (opposing)
                if current['close'] > current['open']:
                    order_blocks.append({
                        'type': 'supply',
                        'high': current['high'],
                        'low': current['low'],
                        'index': i
                    })
    
    return order_blocks
