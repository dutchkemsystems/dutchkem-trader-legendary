"""Integration test: AKShare real data → MLDataLoader → features → labels."""

import asyncio
import pytest
from data.manager import MarketDataManager
from data.models import Timeframe
from apps.ml.data_loader import MLDataLoader
from apps.ml.model import PredictionModel


def test_akshare_provider_registers():
    """AKShareProvider should be in the default registry."""
    dm = MarketDataManager()
    provider_names = [p.name for p in dm.registry.providers]
    assert "akshare" in provider_names, f"AKShare not in providers: {provider_names}"


@pytest.mark.asyncio
async def test_fetch_real_candles():
    """Fetch real daily candles from AKShare. Skips if network unavailable."""
    dm = MarketDataManager()
    try:
        candles = await dm.get_candles("000001", Timeframe.ONE_DAY, limit=100)
    except Exception as e:
        pytest.skip(f"AKShare network unavailable: {e}")

    if len(candles) == 0:
        pytest.skip("AKShare returned no candles (network/geo issue)")

    assert candles[0].symbol == "000001"
    assert candles[0].open > 0
    assert candles[0].close > 0
    assert candles[0].volume > 0
    print(f"  Fetched {len(candles)} candles, last close: {candles[-1].close}")


def test_ml_data_loader_with_stub():
    """MLDataLoader works with StubProvider (always passes)."""
    loader = MLDataLoader()  # Uses default MarketDataManager with AKShare + Stub fallback
    X, y = loader.load_training_data("EURUSD", "1H", limit=300)

    assert X.shape[1] == 10
    assert len(X) > 50
    assert set(y.unique()).issubset({0, 1})
    print(f"  Loaded {X.shape[0]} samples, {X.shape[1]} features")
    print(f"  Label dist: UP={y.sum()}, DOWN={len(y)-y.sum()}")


def test_train_on_stub_data():
    """Train XGBoost and predict — verifies the full pipeline works."""
    loader = MLDataLoader()
    X, y = loader.load_training_data("AAPL", "1H", limit=300)

    model = PredictionModel(model_type="xgboost")
    model.train(X, y)

    pred = model.predict(X.iloc[[-1]].values)
    assert 0.0 <= pred.probability <= 1.0
    assert pred.direction in ("UP", "DOWN")
    print(f"  Prediction: P(UP)={pred.probability:.4f}, direction={pred.direction}")


def test_end_to_end_train_load_predict():
    """Full E2E: load data → train → save → load → predict."""
    import tempfile, os

    loader = MLDataLoader()
    X, y = loader.load_training_data("EURUSD", "1H", limit=300)

    # Train
    model = PredictionModel(model_type="xgboost")
    model.train(X, y)

    # Save — save() expects a file path
    with tempfile.TemporaryDirectory() as tmpdir:
        model_path = os.path.join(tmpdir, "model.pkl")
        model.save(model_path)
        assert os.path.exists(model_path)

        # Load
        loaded = PredictionModel.load(model_path)
        pred = loaded.predict(X.iloc[[-1]].values)
        assert 0.0 <= pred.probability <= 1.0
        print(f"  E2E OK: saved -> loaded -> P(UP)={pred.probability:.4f}")
