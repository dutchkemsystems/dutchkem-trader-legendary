import pytest
import numpy as np
import pickle
from pathlib import Path
from apps.ml.model import PredictionModel, Prediction
from apps.ml.predictor import MLPredictor, MLPrediction


def test_model_creates_xgboost_by_default():
    model = PredictionModel()
    assert model.model is not None
    assert model.model_type == "xgboost"


def test_model_creates_lightgbm():
    model = PredictionModel(model_type="lightgbm")
    assert model.model is not None
    assert model.model_type == "lightgbm"


def test_model_rejects_unknown_type():
    with pytest.raises(ValueError, match="Unknown model type"):
        PredictionModel(model_type="random_forest")


def test_model_train_and_predict():
    model = PredictionModel()
    X = np.random.rand(100, 10)
    y = np.random.randint(0, 2, 100)
    model.train(X, y)
    pred = model.predict(X[:1])
    assert isinstance(pred, Prediction)
    assert 0.0 <= pred.probability <= 1.0
    assert pred.direction in ("UP", "DOWN")
    assert pred.model_name == "xgboost"


def test_model_predict_up_direction():
    model = PredictionModel()
    np.random.seed(42)
    X = np.random.rand(100, 10)
    y = np.array([1] * 80 + [0] * 20)
    model.train(X, y)
    pred = model.predict(X[:1])
    assert pred.direction == "UP"
    assert pred.probability > 0.5


def test_model_predict_down_direction():
    model = PredictionModel()
    np.random.seed(42)
    X = np.random.rand(100, 10)
    y = np.array([0] * 80 + [1] * 20)
    model.train(X, y)
    pred = model.predict(X[:1])
    assert pred.direction == "DOWN"
    assert pred.probability < 0.5


def test_model_save_load(tmp_path):
    model = PredictionModel()
    X = np.random.rand(50, 10)
    y = np.random.randint(0, 2, 50)
    model.train(X, y)
    save_path = tmp_path / "model.pkl"
    model.save(str(save_path))
    assert save_path.exists()

    loaded = PredictionModel.load(str(save_path))
    pred = loaded.predict(X[:1])
    assert pred.probability is not None
    assert 0.0 <= pred.probability <= 1.0
    assert loaded.model_type == "xgboost"


def test_model_save_load_lightgbm(tmp_path):
    model = PredictionModel(model_type="lightgbm")
    X = np.random.rand(50, 10)
    y = np.random.randint(0, 2, 50)
    model.train(X, y)
    model.save(str(tmp_path / "lgb.pkl"))
    loaded = PredictionModel.load(str(tmp_path / "lgb.pkl"))
    assert loaded.model_type == "lightgbm"
    pred = loaded.predict(X[:1])
    assert 0.0 <= pred.probability <= 1.0


def test_model_untrained_predict_raises():
    model = PredictionModel()
    X = np.random.rand(1, 10)
    with pytest.raises(Exception):
        model.predict(X)


def test_predictor_train_and_predict():
    predictor = MLPredictor()
    X = np.random.rand(100, 10)
    y = np.random.randint(0, 2, 100)
    predictor.train(X, y)
    result = predictor.predict_from_features(X[:1])
    assert isinstance(result, MLPrediction)
    assert 0.0 <= result.p_up <= 1.0
    assert result.direction in ("UP", "DOWN")
    assert result.features_used == 10


def test_predictor_reshapes_1d_input():
    predictor = MLPredictor()
    X = np.random.rand(100, 10)
    y = np.random.randint(0, 2, 100)
    predictor.train(X, y)
    single = X[0]
    result = predictor.predict_from_features(single)
    assert isinstance(result, MLPrediction)
    assert result.features_used == 10


def test_predictor_uses_lightgbm():
    predictor = MLPredictor(model_type="lightgbm")
    X = np.random.rand(100, 10)
    y = np.random.randint(0, 2, 100)
    predictor.train(X, y)
    result = predictor.predict_from_features(X[:1])
    assert result.model_name == "lightgbm"
