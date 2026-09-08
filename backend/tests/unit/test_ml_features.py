import pytest
import pandas as pd
import numpy as np
from apps.ml.features import FeatureExtractor

def test_feature_extractor_returns_10_features():
    dates = pd.date_range('2024-01-01', periods=100, freq='1h')
    np.random.seed(42)
    price = 1.10 + np.cumsum(np.random.randn(100) * 0.001)
    df = pd.DataFrame({
        'open': price + np.random.randn(100) * 0.0005,
        'high': price + abs(np.random.randn(100) * 0.001),
        'low': price - abs(np.random.randn(100) * 0.001),
        'close': price,
        'volume': np.random.randint(1000, 10000, 100)
    }, index=dates)
    extractor = FeatureExtractor()
    features = extractor.extract(df)
    assert features.shape[1] == 10

def test_feature_names():
    extractor = FeatureExtractor()
    expected = ['rsi', 'macd_hist', 'bb_width', 'atr_pct', 'volume_ratio',
                'price_momentum', 'volatility_regime', 'trend_strength',
                'support_distance', 'resistance_distance']
    assert extractor.feature_names == expected

def test_extract_requires_minimum_rows():
    extractor = FeatureExtractor()
    df = pd.DataFrame({'open': [1]*5, 'high': [1]*5, 'low': [1]*5, 'close': [1]*5, 'volume': [1]*5})
    with pytest.raises(ValueError, match="minimum.*30 rows"):
        extractor.extract(df)
