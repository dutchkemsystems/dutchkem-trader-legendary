"""Renko chart generator."""

import pandas as pd
import numpy as np


def generate_renko(data: pd.DataFrame, brick_size_pips: float, pip_value: float = 0.0001) -> pd.DataFrame:
    """Generate Renko chart from OHLCV data."""
    brick_size = brick_size_pips * pip_value
    renko_bars = []
    last_price = data['close'].iloc[0]
    
    for _, row in data.iterrows():
        price = row['close']
        while price > last_price + brick_size:
            last_price += brick_size
            renko_bars.append({'open': last_price - brick_size, 'close': last_price, 'direction': 1})
        while price < last_price - brick_size:
            last_price -= brick_size
            renko_bars.append({'open': last_price + brick_size, 'close': last_price, 'direction': -1})
    
    return pd.DataFrame(renko_bars) if renko_bars else pd.DataFrame()
