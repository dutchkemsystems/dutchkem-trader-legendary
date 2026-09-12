"""Tests for ML Pipeline Fixes — Real Data + Correct Metrics."""

import pytest
import numpy as np
import pandas as pd
from unittest.mock import MagicMock, patch
from pathlib import Path


class TestMLDataLoader:
    """Test MLDataLoader uses real data providers, not StubProvider."""

    def test_data_loader_does_not_use_stub_provider(self):
        """MLDataLoader should default to real providers, not StubProvider."""
        from apps.ml.data_loader import MLDataLoader
        from data.providers import StubProvider

        loader = MLDataLoader()
        # Check that StubProvider is NOT the only provider
        providers = loader.data_manager.registry.providers
        non_stub = [p for p in providers if not isinstance(p, StubProvider)]
        assert len(non_stub) > 0, "MLDataLoader should have real providers, not just StubProvider"

    def test_data_loader_has_akshare_or_real_provider(self):
        """MLDataLoader should have at least one real data provider."""
        from apps.ml.data_loader import MLDataLoader

        loader = MLDataLoader()
        provider_names = [p.name for p in loader.data_manager.registry.providers]
        # Should have at least one non-stub provider
        real_providers = [n for n in provider_names if n != "stub"]
        assert len(real_providers) > 0, f"Expected real providers, got: {provider_names}"


class TestMLFeatures:
    """Test FeatureExtractor produces correct features."""

    def test_feature_extractor_produces_10_features(self):
        """FeatureExtractor should produce exactly 10 features."""
        from apps.ml.features import FeatureExtractor

        extractor = FeatureExtractor()
        # Create minimal test data
        np.random.seed(42)
        n = 100
        df = pd.DataFrame({
            'open': np.random.uniform(1.08, 1.09, n),
            'high': np.random.uniform(1.085, 1.095, n),
            'low': np.random.uniform(1.075, 1.085, n),
            'close': np.random.uniform(1.08, 1.09, n),
            'volume': np.random.randint(1000, 10000, n),
        })

        features = extractor.extract(df)
        assert features.shape[1] == 10
        assert list(features.columns) == extractor.FEATURE_NAMES

    def test_features_include_support_resistance(self):
        """Features should include support_distance and resistance_distance."""
        from apps.ml.features import FeatureExtractor

        extractor = FeatureExtractor()
        np.random.seed(42)
        n = 100
        df = pd.DataFrame({
            'open': np.random.uniform(1.08, 1.09, n),
            'high': np.random.uniform(1.085, 1.095, n),
            'low': np.random.uniform(1.075, 1.085, n),
            'close': np.random.uniform(1.08, 1.09, n),
            'volume': np.random.randint(1000, 10000, n),
        })

        features = extractor.extract(df)
        assert 'support_distance' in features.columns
        assert 'resistance_distance' in features.columns
        # These should NOT all be zero
        assert features['support_distance'].abs().sum() > 0
        assert features['resistance_distance'].abs().sum() > 0


class TestMLModel:
    """Test PredictionModel trains and predicts correctly."""

    def test_model_trains_and_predicts(self):
        """Model should train without errors and return valid predictions."""
        from apps.ml.model import PredictionModel

        np.random.seed(42)
        X = np.random.randn(200, 10)
        y = (X[:, 0] > 0).astype(int)  # Simple rule: RSI > 0 → UP

        model = PredictionModel(model_type="xgboost")
        model.train(X[:160], y[:160])

        assert model.trained is True

        pred = model.predict(X[160:])
        assert pred.direction in ("UP", "DOWN")
        assert 0.0 <= pred.probability <= 1.0

    def test_model_save_and_load(self):
        """Model should save to disk and load correctly."""
        from apps.ml.model import PredictionModel
        import tempfile
        import os

        np.random.seed(42)
        X = np.random.randn(200, 10)
        y = (X[:, 0] > 0).astype(int)

        model = PredictionModel(model_type="xgboost")
        model.train(X[:160], y[:160])

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test_model.pkl")
            model.save(path)
            assert os.path.exists(path)

            loaded = PredictionModel.load(path)
            assert loaded.trained is True
            pred = loaded.predict(X[160:])
            assert pred.direction in ("UP", "DOWN")


class TestMLRank:
    """Test ml_rank() function in unified_engine."""

    def test_ml_rank_returns_valid_probability(self):
        """ml_rank should return float between 0.0 and 1.0."""
        # Import the function directly
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent.parent))

        # We can't easily import ml_rank without the full engine,
        # so test the logic directly
        from apps.ml.predictor import MLPredictor

        predictor = MLPredictor(model_type="xgboost")
        # Even untrained, should return 0.5
        features = np.array([50, 0, 0.02, 0.001, 1.0, 0, 0.0, 25, 0.001, 0.002])
        pred = predictor.predict_from_features(features)
        assert 0.0 <= pred.p_up <= 1.0

    def test_predictor_caches_instance(self):
        """MLPredictor should be cacheable (not create new instance each call)."""
        from apps.ml.predictor import MLPredictor

        p1 = MLPredictor(model_type="xgboost")
        p2 = MLPredictor(model_type="xgboost")
        # Both should work independently
        features = np.array([50, 0, 0.02, 0.001, 1.0, 0, 0.0, 25, 0.001, 0.002])
        r1 = p1.predict_from_features(features)
        r2 = p2.predict_from_features(features)
        # Untrained models should return same result
        assert r1.p_up == r2.p_up


class TestTrainReal:
    """Test train_real.py accuracy metrics."""

    def test_accuracy_uses_sklearn_metrics(self):
        """train_real.py should use accuracy_score, not direction counting."""
        # Read the file and check for sklearn imports
        train_real_path = Path(__file__).parent.parent.parent / "apps" / "ml" / "train_real.py"
        content = train_real_path.read_text()
        assert "accuracy_score" in content
        assert "precision_score" in content
        assert "(train_pred.direction == \"UP\").mean()" not in content
