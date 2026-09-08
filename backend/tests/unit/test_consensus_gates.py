import pytest
from apps.consensus.gates import ConsensusGates, GateResult


# ── GateResult basics ──────────────────────────────────────────────

def test_gate_result_is_dataclass():
    r = GateResult(gate_name="x", passed=True, value=1.0, reason="ok")
    assert r.passed is True
    assert r.gate_name == "x"


# ── Gate 1: ML Model ──────────────────────────────────────────────

def test_gate1_ml_model_no_predictor():
    gates = ConsensusGates()
    result = gates.check_ml_model([0.5] * 10)
    assert result.gate_name == "ml_model"
    assert result.passed is True
    assert "not available" in result.reason


def test_gate1_ml_model_passes():
    class FakeML:
        def predict_from_features(self, features):
            from apps.ml.predictor import MLPrediction
            return MLPrediction(p_up=0.72, direction="UP", model_name="fake", features_used=10)

    gates = ConsensusGates(ml_predictor=FakeML())
    result = gates.check_ml_model([0.5] * 10)
    assert result.passed is True
    assert abs(result.value - 0.72) < 0.001


def test_gate1_ml_model_fails():
    class FakeML:
        def predict_from_features(self, features):
            from apps.ml.predictor import MLPrediction
            return MLPrediction(p_up=0.35, direction="DOWN", model_name="fake", features_used=10)

    gates = ConsensusGates(ml_predictor=FakeML())
    result = gates.check_ml_model([0.5] * 10, p_up_threshold=0.5)
    assert result.passed is False
    assert abs(result.value - 0.35) < 0.001


def test_gate1_ml_model_exception():
    class BrokenML:
        def predict_from_features(self, features):
            raise RuntimeError("model crash")

    gates = ConsensusGates(ml_predictor=BrokenML())
    result = gates.check_ml_model([0.5] * 10)
    assert result.passed is False
    assert "error" in result.reason.lower()


# ── Gate 2: LLM Consensus ────────────────────────────────────────

def test_gate2_llm_consensus_passes():
    gates = ConsensusGates()
    result = gates.check_llm_consensus({"agreement_pct": 0.80})
    assert result.gate_name == "llm_consensus"
    assert result.passed is True


def test_gate2_llm_consensus_fails():
    gates = ConsensusGates()
    result = gates.check_llm_consensus({"agreement_pct": 0.55})
    assert result.passed is False


def test_gate2_llm_consensus_no_key():
    gates = ConsensusGates()
    result = gates.check_llm_consensus({})
    assert result.passed is False
    assert abs(result.value - 0.0) < 0.001


# ── Gate 3: Sentiment ─────────────────────────────────────────────

def test_gate3_sentiment_passes():
    from apps.analysts.base import AnalystResult
    gates = ConsensusGates()
    results = [
        AnalystResult("sentiment_news", "EURUSD", "1H", "BUY", 0.85, "positive"),
        AnalystResult("sentiment_social", "EURUSD", "1H", "BUY", 0.78, "positive"),
    ]
    result = gates.check_sentiment(results)
    assert result.passed is True
    assert result.gate_name == "sentiment"


def test_gate3_sentiment_fails():
    from apps.analysts.base import AnalystResult
    gates = ConsensusGates()
    results = [
        AnalystResult("sentiment_news", "EURUSD", "1H", "BUY", 0.50, "weak"),
    ]
    result = gates.check_sentiment(results)
    assert result.passed is False


def test_gate3_sentiment_no_sentiment_analyst():
    from apps.analysts.base import AnalystResult
    gates = ConsensusGates()
    results = [
        AnalystResult("market", "EURUSD", "1H", "BUY", 0.8, "tech"),
    ]
    result = gates.check_sentiment(results)
    assert result.passed is True
    assert "no sentiment" in result.reason.lower()


# ── Gate 4: Technical ─────────────────────────────────────────────

def test_gate4_technical_passes():
    from apps.analysts.base import AnalystResult
    gates = ConsensusGates()
    results = [
        AnalystResult("technical", "EURUSD", "1H", "BUY", 0.82, "rsi"),
        AnalystResult("market_structure", "EURUSD", "1H", "BUY", 0.75, "structure"),
    ]
    result = gates.check_technical(results)
    assert result.passed is True
    assert result.gate_name == "technical"


def test_gate4_technical_fails():
    from apps.analysts.base import AnalystResult
    gates = ConsensusGates()
    results = [
        AnalystResult("technical", "EURUSD", "1H", "BUY", 0.55, "weak"),
    ]
    result = gates.check_technical(results)
    assert result.passed is False


def test_gate4_no_technical_analyst():
    from apps.analysts.base import AnalystResult
    gates = ConsensusGates()
    results = [
        AnalystResult("sentiment", "EURUSD", "1H", "BUY", 0.8, "pos"),
    ]
    result = gates.check_technical(results)
    assert result.passed is True
    assert "no technical" in result.reason.lower()


# ── Gate 5: Edge ──────────────────────────────────────────────────

def test_gate5_edge_above_threshold():
    gates = ConsensusGates()
    result = gates.check_edge(p_up=0.65, market_price=0.55)
    assert result.gate_name == "edge"
    assert result.passed is True
    assert abs(result.value - 0.10) < 0.001


def test_gate5_edge_below_threshold():
    gates = ConsensusGates()
    result = gates.check_edge(p_up=0.52, market_price=0.55)
    assert result.passed is False


def test_gate5_edge_exact_threshold_fails():
    """Edge exactly at threshold (0.02) fails because > is strict.
    Due to float precision, 0.57-0.55 ≈ 0.019999... which is < 0.02."""
    gates = ConsensusGates()
    result = gates.check_edge(p_up=0.57, market_price=0.55)
    assert result.passed is False
    assert abs(result.value - 0.02) < 0.001


def test_gate5_edge_just_above_threshold():
    """Edge clearly above 0.02 threshold passes."""
    gates = ConsensusGates()
    result = gates.check_edge(p_up=0.58, market_price=0.55)
    assert result.passed is True
    assert result.value > 0.02


def test_gate5_edge_with_black_scholes():
    class FakeBS:
        def calculate_edge(self, p_up, market_price):
            return p_up - market_price - 0.01  # extra cost

    gates = ConsensusGates(black_scholes=FakeBS())
    # 0.62 - 0.55 - 0.01 = 0.06, clearly above threshold
    result = gates.check_edge(p_up=0.62, market_price=0.55)
    assert result.passed is True
    assert abs(result.value - 0.06) < 0.001


# ── Gate 6: Market Regime ────────────────────────────────────────

def test_gate6_regime_chop_blocked():
    from apps.consensus.regime import MarketRegimeDetector
    gates = ConsensusGates(regime_detector=MarketRegimeDetector())
    result = gates.check_market_regime(adx=15.0)
    assert result.gate_name == "regime"
    assert result.passed is False
    assert result.value == "chop"


def test_gate6_regime_trending_ok():
    from apps.consensus.regime import MarketRegimeDetector
    gates = ConsensusGates(regime_detector=MarketRegimeDetector())
    result = gates.check_market_regime(adx=30.0)
    assert result.passed is True
    assert result.value == "trending"


def test_gate6_regime_no_detector():
    gates = ConsensusGates()
    result = gates.check_market_regime()
    assert result.passed is True
    assert "no regime detector" in result.reason.lower()


def test_gate6_regime_adverse_selection():
    from apps.consensus.regime import MarketRegimeDetector
    gates = ConsensusGates(regime_detector=MarketRegimeDetector())
    result = gates.check_market_regime(
        spread_bps=12.0,
        volume_imbalance=0.8,
    )
    assert result.passed is False
    assert result.value == "adverse_selection"


# ── Gate 7: Liquidity Limits ─────────────────────────────────────

def test_gate7_liquidity_passes():
    gates = ConsensusGates()
    result = gates.check_liquidity_limits({
        "current_positions": 5,
        "max_positions": 10,
    })
    assert result.gate_name == "liquidity"
    assert result.passed is True


def test_gate7_liquidity_fails():
    gates = ConsensusGates()
    result = gates.check_liquidity_limits({
        "current_positions": 10,
        "max_positions": 10,
    })
    assert result.passed is False


def test_gate7_liquidity_empty():
    gates = ConsensusGates()
    result = gates.check_liquidity_limits({})
    # defaults: 0 < 10 → passes
    assert result.passed is True


# ── evaluate_all ──────────────────────────────────────────────────

def test_evaluate_all_all_pass():
    from apps.consensus.regime import MarketRegimeDetector
    gates = ConsensusGates(regime_detector=MarketRegimeDetector())
    result = gates.evaluate_all(
        features=[0.5] * 10,
        consensus={"agreement_pct": 0.80},
        analyst_results=[],
        p_up=0.65,
        market_price=0.55,
        regime_kwargs={"adx": 30.0},
        risk_status={"current_positions": 5, "max_positions": 10},
    )
    assert result["trade_allowed"] is True
    assert result["passed_count"] == 7
    assert result["total_gates"] == 7


def test_evaluate_all_regime_blocks():
    from apps.consensus.regime import MarketRegimeDetector
    gates = ConsensusGates(regime_detector=MarketRegimeDetector())
    result = gates.evaluate_all(
        p_up=0.65,
        market_price=0.55,
        consensus={"agreement_pct": 0.80},
        analyst_results=[],
        regime_kwargs={"adx": 15.0},
        risk_status={"current_positions": 5, "max_positions": 10},
    )
    assert result["trade_allowed"] is False
    assert result["gates"]["regime"]["passed"] is False


def test_evaluate_all_low_edge_blocks():
    gates = ConsensusGates()
    result = gates.evaluate_all(
        p_up=0.53,
        market_price=0.55,
        consensus={"agreement_pct": 0.80},
        analyst_results=[],
        regime_kwargs={"adx": 30.0},
        risk_status={"current_positions": 5, "max_positions": 10},
    )
    assert result["trade_allowed"] is False
    assert result["gates"]["edge"]["passed"] is False


def test_evaluate_all_gates_dict_structure():
    gates = ConsensusGates()
    result = gates.evaluate_all()
    expected_keys = {"ml_model", "llm_consensus", "sentiment", "technical", "edge", "regime", "liquidity"}
    assert set(result["gates"].keys()) == expected_keys
    for gk, gv in result["gates"].items():
        assert "passed" in gv
        assert "value" in gv
        assert "reason" in gv
