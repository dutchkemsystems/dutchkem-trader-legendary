"""Shared test fixtures for scalping strategy tests."""

import pytest
import pandas as pd
import numpy as np


@pytest.fixture
def mock_ohlcv():
    """Generate mock OHLCV data for testing.
    
    Creates 200 bars of realistic-looking price data
    with proper OHLCV relationships.
    """
    np.random.seed(42)
    dates = pd.date_range('2026-01-01', periods=200, freq='5min')
    base_price = 1.1000
    returns = np.random.randn(200) * 0.0005
    prices = base_price + np.cumsum(returns)
    
    return pd.DataFrame({
        'open': prices + np.random.randn(200) * 0.0001,
        'high': prices + abs(np.random.randn(200) * 0.0002),
        'low': prices - abs(np.random.randn(200) * 0.0002),
        'close': prices,
        'volume': np.random.randint(100, 1000, 200)
    }, index=dates)


@pytest.fixture
def mock_data_dict(mock_ohlcv):
    """Dict of timeframe -> DataFrame for strategy testing.
    
    All timeframes use the same mock data for simplicity.
    In real tests, each timeframe would have different characteristics.
    """
    return {
        'M1': mock_ohlcv,
        'M5': mock_ohlcv,
        'M15': mock_ohlcv,
        'H1': mock_ohlcv,
        'H4': mock_ohlcv,
    }
