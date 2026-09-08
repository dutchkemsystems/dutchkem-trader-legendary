"""Tests for MLDataLoader — real data wiring for ML training."""

import pytest
import pandas as pd
import numpy as np
from apps.ml.data_loader import MLDataLoader, TIMEFRAME_MAP
from apps.ml.model import PredictionModel


def _make_realistic_candles(n: int = 200) -> pd.DataFrame:
    """Generate realistic OHLCV candle data (not random walk)."""
    np.random.seed(42)
    dates = pd.date_range("2023-01-01", periods=n, freq="1h")
    base = 1.10
    # Simulate trending + mean-reverting price
    returns = np.random.randn(n) * 0.0005
    returns += 0.0001 * np.sin(np.arange(n) / 20)  # cyclical component
    price = base + np.cumsum(returns)

    df = pd.DataFrame(
        {
            "open": price + np.random.randn(n) * 0.0001,
            "high": price + np.abs(np.random.randn(n) * 0.0005),
            "low": price - np.abs(np.random.randn(n) * 0.0005),
            "close": price,
            "volume": np.random.randint(1000, 10000, n),
        },
        index=dates,
    )
    return df


# ── TIMEFRAME_MAP ──


def test_timeframe_map_has_common_strings():
    assert TIMEFRAME_MAP["1H"] is not None
    assert TIMEFRAME_MAP["1D"] is not None
    assert TIMEFRAME_MAP["15M"] is not None


def test_timeframe_map_legacy_aliases():
    assert TIMEFRAME_MAP["Daily"] == TIMEFRAME_MAP["1D"]
    assert TIMEFRAME_MAP["hourly"] == TIMEFRAME_MAP["1H"]


# ── load_training_data_from_df ──


def test_load_from_df_returns_features_and_labels():
    loader = MLDataLoader()
    df = _make_realistic_candles(200)
    X, y = loader.load_training_data_from_df(df)

    assert X.shape[1] == 10  # 10 features
    assert len(X) == len(y)
    assert len(X) > 100  # Should have plenty after NaN drop
    assert set(y.unique()).issubset({0, 1})  # Binary labels only


def test_load_from_df_label_distribution():
    loader = MLDataLoader()
    df = _make_realistic_candles(300)
    X, y = loader.load_training_data_from_df(df, forecast_period=5)
    ratio = y.mean()
    # With random walk, expect roughly 50/50 ± 15%
    assert 0.35 < ratio < 0.65, f"Label ratio {ratio:.2f} looks wrong"


def test_load_from_df_feature_names_match():
    loader = MLDataLoader()
    df = _make_realistic_candles(200)
    X, y = loader.load_training_data_from_df(df)
    assert list(X.columns) == loader.extractor.feature_names


def test_load_from_df_too_few_rows():
    loader = MLDataLoader()
    df = _make_realistic_candles(10)
    with pytest.raises(ValueError, match="Need at least"):
        loader.load_training_data_from_df(df)


# ── load_training_data (StubProvider fallback) ──


def test_load_training_data_stub_provider():
    """Test with StubProvider (default) — validates the full pipeline."""
    loader = MLDataLoader()  # No data_manager → StubProvider
    X, y = loader.load_training_data("EURUSD", "1H", limit=200)

    assert X.shape[1] == 10
    assert len(X) > 50
    assert set(y.unique()).issubset({0, 1})


# ── End-to-end: load → train → predict ──


def test_end_to_end_stub():
    """Full pipeline: StubData → Features → Train → Predict."""
    loader = MLDataLoader()
    X, y = loader.load_training_data("AAPL", "1H", limit=300)

    model = PredictionModel(model_type="xgboost")
    model.train(X, y)

    pred = model.predict(X.iloc[[-1]].values)
    assert 0.0 <= pred.probability <= 1.0
    assert pred.direction in ("UP", "DOWN")


# ── Custom provider injection ──


def test_custom_data_manager():
    """Test that a custom data manager can be injected."""
    from data.manager import MarketDataManager

    loader = MLDataLoader(data_manager=MarketDataManager())
    X, y = loader.load_training_data("EURUSD", "1H", limit=150)
    assert X.shape[1] == 10
