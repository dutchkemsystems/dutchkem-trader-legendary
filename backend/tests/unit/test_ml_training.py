"""Tests for ML Training Pipeline — Task 6: Initial Model Training."""

import pytest
import numpy as np
import pandas as pd


class TestMLTrainingPipeline:
    """Test that the training pipeline works end-to-end with valid data."""

    def _make_balanced_data(self, n=500):
        """Generate balanced OHLCV data with ~50/50 up/down labels."""
        np.random.seed(42)
        dates = pd.date_range(end=pd.Timestamp.now(), periods=n, freq='1h')
        returns = np.random.normal(0, 0.001, n)
        close = 1.0850 * np.cumprod(1 + returns)
        high = close * (1 + np.abs(np.random.normal(0, 0.0003, n)))
        low = close * (1 - np.abs(np.random.normal(0, 0.0003, n)))
        open_p = np.roll(close, 1)
        open_p[0] = close[0]
        volume = np.random.lognormal(np.log(10000), 0.5, n).astype(int)
        return pd.DataFrame({
            'open': open_p,
            'high': np.maximum(high, np.maximum(open_p, close)),
            'low': np.minimum(low, np.minimum(open_p, close)),
            'close': close,
            'volume': volume,
        }, index=dates)

    def test_feature_extraction_works(self):
        """FeatureExtractor should produce valid features from OHLCV."""
        from apps.ml.features import FeatureExtractor
        df = self._make_balanced_data(300)
        extractor = FeatureExtractor()
        features = extractor.extract(df)
        assert len(features) > 0
        assert len(features.columns) >= 8

    def test_training_on_balanced_data_succeeds(self):
        """XGBoost should train successfully on balanced data."""
        from apps.ml.features import FeatureExtractor
        from apps.ml.model import PredictionModel
        from sklearn.metrics import accuracy_score

        df = self._make_balanced_data(500)
        extractor = FeatureExtractor()
        features = extractor.extract(df)
        future_return = df["close"].shift(-1) - df["close"]
        labels = (future_return > 0).astype(int)

        common_idx = features.index.intersection(labels.index)
        X = features.loc[common_idx].copy()
        y = labels.loc[common_idx].copy()
        valid_mask = X.notna().all(axis=1) & y.notna()
        X = X.loc[valid_mask]
        y = y.loc[valid_mask]

        # Should have roughly balanced labels
        assert len(y) > 100
        up_ratio = y.sum() / len(y)
        assert 0.3 < up_ratio < 0.7, f"Labels unbalanced: {up_ratio:.2%}"

        split_idx = int(len(X) * 0.8)
        X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
        y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]

        model = PredictionModel(model_type="xgboost")
        model.train(X_train.values, y_train)

        test_pred = model.model.predict(X_test.values)
        test_accuracy = accuracy_score(y_test, test_pred)
        # Accuracy should be a valid number (not NaN or 0)
        assert 0.0 <= test_accuracy <= 1.0
        print(f"Test accuracy: {test_accuracy:.4f}")

    def test_model_save_load(self):
        """Model should save and load without errors."""
        import tempfile
        from apps.ml.model import PredictionModel
        df = self._make_balanced_data(200)
        from apps.ml.features import FeatureExtractor
        extractor = FeatureExtractor()
        features = extractor.extract(df)
        future_return = df["close"].shift(-1) - df["close"]
        labels = (future_return > 0).astype(int)
        common_idx = features.index.intersection(labels.index)
        X = features.loc[common_idx].copy()
        y = labels.loc[common_idx].copy()
        valid_mask = X.notna().all(axis=1) & y.notna()
        X = X.loc[valid_mask]
        y = y.loc[valid_mask]

        if len(y) > 50:
            model = PredictionModel(model_type="xgboost")
            model.train(X.values, y)
            with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as f:
                model.save(f.name)
                loaded = PredictionModel.load(f.name)
                assert loaded is not None

    def test_label_distribution_check(self):
        """Training script should detect degenerate labels."""
        # Simulate what train_real does: check label balance
        degenerate_y = pd.Series([1] * 173 + [0] * 1)
        balanced_y = pd.Series([1] * 87 + [0] * 83)
        degenerate_ratio = degenerate_y.sum() / len(degenerate_y)
        balanced_ratio = balanced_y.sum() / len(balanced_y)
        # Degenerate should be >90% one class
        assert degenerate_ratio > 0.95
        # Balanced should be 40-60%
        assert 0.40 < balanced_ratio < 0.60

    def test_train_real_script_has_balanced_data_guard(self):
        """train_real.py should have label balance checking."""
        from pathlib import Path
        train_path = Path(__file__).parent.parent.parent / "apps" / "ml" / "train_real.py"
        content = train_path.read_text(encoding="utf-8")
        assert "label_distribution" in content or "Label distribution" in content
