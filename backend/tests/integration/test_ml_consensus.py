import pytest
import numpy as np
from apps.consensus.gates import ConsensusGates
from apps.ml.predictor import MLPredictor


def test_ml_gate_with_real_predictor():
    predictor = MLPredictor()
    X = np.random.rand(100, 10)
    y = np.random.randint(0, 2, 100)
    predictor.train(X, y)

    gates = ConsensusGates(ml_predictor=predictor)
    result = gates.check_ml_model(X[:1])
    assert result.gate_name == "ml_model"
    assert 0.0 <= result.value <= 1.0
    assert isinstance(result.passed, bool)
    assert result.reason.startswith("P(UP)=")


def test_ml_gate_value_bounded():
    predictor = MLPredictor()
    X = np.random.rand(200, 15)
    y = np.random.randint(0, 2, 200)
    predictor.train(X, y)

    gates = ConsensusGates(ml_predictor=predictor)
    for i in range(10):
        result = gates.check_ml_model(X[i : i + 1])
        assert 0.0 <= result.value <= 1.0, f"Iteration {i}: value={result.value}"


def test_ml_gate_high_threshold_blocks():
    predictor = MLPredictor()
    X = np.random.rand(100, 10)
    y = np.random.randint(0, 2, 100)
    predictor.train(X, y)

    gates = ConsensusGates(ml_predictor=predictor)
    result = gates.check_ml_model(X[:1], p_up_threshold=0.99)
    assert result.passed is False


def test_ml_gate_no_predictor_passes():
    gates = ConsensusGates()
    result = gates.check_ml_model([0.5] * 10)
    assert result.passed is True
    assert "not available" in result.reason


def test_evaluate_all_with_ml_predictor():
    predictor = MLPredictor()
    X = np.random.rand(100, 10)
    y = np.random.randint(0, 2, 100)
    predictor.train(X, y)

    gates = ConsensusGates(ml_predictor=predictor)
    result = gates.evaluate_all(
        features=X[:1],
        consensus={"agreement_pct": 0.80},
        analyst_results=[],
        p_up=0.65,
        market_price=0.55,
        regime_kwargs={"adx": 30.0},
        risk_status={"current_positions": 5, "max_positions": 10},
    )
    assert "ml_model" in result["gates"]
    assert 0.0 <= result["gates"]["ml_model"]["value"] <= 1.0
