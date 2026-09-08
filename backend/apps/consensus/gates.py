from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class GateResult:
    gate_name: str
    passed: bool
    value: Any
    reason: str


class ConsensusGates:
    MIN_EDGE_AFTER_COSTS = 0.02
    MIN_SENTIMENT_CONFIDENCE = 0.70
    MIN_TECHNICAL_CONFIDENCE = 0.70

    def __init__(self, ml_predictor=None, black_scholes=None, regime_detector=None):
        self.ml_predictor = ml_predictor
        self.black_scholes = black_scholes
        self.regime_detector = regime_detector

    def check_ml_model(self, features, p_up_threshold=0.5) -> GateResult:
        """Gate 1: ML model predicts P(UP)"""
        if not self.ml_predictor:
            return GateResult("ml_model", True, 0.5, "ML model not available, passing")
        try:
            pred = self.ml_predictor.predict_from_features(features)
            passed = pred.p_up >= p_up_threshold
            return GateResult(
                "ml_model",
                passed,
                pred.p_up,
                f"P(UP)={pred.p_up:.3f}, threshold={p_up_threshold}",
            )
        except Exception as e:
            return GateResult("ml_model", False, 0.0, f"ML error: {e}")

    def check_llm_consensus(self, consensus_result: Dict) -> GateResult:
        """Gate 2: LLM analyst confirms direction"""
        agreement = consensus_result.get("agreement_pct", 0)
        passed = agreement >= 0.70
        return GateResult(
            "llm_consensus",
            passed,
            agreement,
            f"Agreement={agreement:.1%}, threshold=70%",
        )

    def check_sentiment(self, analyst_results: List) -> GateResult:
        """Gate 3: Sentiment analysis agrees (>70% confidence)"""
        sentiment_results = [
            r for r in analyst_results if "sentiment" in r.analyst_name.lower()
        ]
        if not sentiment_results:
            return GateResult(
                "sentiment", True, 0.0, "No sentiment analyst, passing"
            )
        avg_conf = sum(r.confidence for r in sentiment_results) / len(
            sentiment_results
        )
        passed = avg_conf >= self.MIN_SENTIMENT_CONFIDENCE
        return GateResult(
            "sentiment",
            passed,
            avg_conf,
            f"Avg confidence={avg_conf:.3f}, threshold={self.MIN_SENTIMENT_CONFIDENCE}",
        )

    def check_technical(self, analyst_results: List) -> GateResult:
        """Gate 4: Technical indicators confirm (>70%)"""
        tech_results = [
            r
            for r in analyst_results
            if "technical" in r.analyst_name.lower()
            or "market" in r.analyst_name.lower()
        ]
        if not tech_results:
            return GateResult(
                "technical", True, 0.0, "No technical analyst, passing"
            )
        avg_conf = sum(r.confidence for r in tech_results) / len(tech_results)
        passed = avg_conf >= self.MIN_TECHNICAL_CONFIDENCE
        return GateResult(
            "technical",
            passed,
            avg_conf,
            f"Avg confidence={avg_conf:.3f}, threshold={self.MIN_TECHNICAL_CONFIDENCE}",
        )

    def check_edge(self, p_up: float, market_price: float) -> GateResult:
        """Gate 5: Edge = P(UP) - price > MIN_EDGE_AFTER_COSTS"""
        if self.black_scholes:
            edge = self.black_scholes.calculate_edge(p_up, market_price)
        else:
            edge = p_up - market_price
        passed = edge > self.MIN_EDGE_AFTER_COSTS
        return GateResult(
            "edge",
            passed,
            edge,
            f"Edge={edge:.4f}, threshold={self.MIN_EDGE_AFTER_COSTS}",
        )

    def check_market_regime(self, **kwargs) -> GateResult:
        """Gate 6: Market regime blocking (chop, trap, adverse_selection)"""
        if not self.regime_detector:
            return GateResult("regime", True, "normal", "No regime detector, passing")
        result = self.regime_detector.detect(**kwargs)
        passed = not result.blocked
        return GateResult(
            "regime",
            passed,
            result.regime.value,
            f"Regime={result.regime.value}, blocked={result.blocked}",
        )

    def check_liquidity_limits(self, risk_status: dict) -> GateResult:
        """Gate 7: Liquidity and position limits pass"""
        max_positions = risk_status.get("max_positions", 10)
        current_positions = risk_status.get("current_positions", 0)
        passed = current_positions < max_positions
        return GateResult(
            "liquidity",
            passed,
            current_positions,
            f"Positions={current_positions}/{max_positions}",
        )

    def evaluate_all(self, **kwargs) -> dict:
        """Run all 7 gates and return combined result"""
        gates = [
            self.check_ml_model(kwargs.get("features", [])),
            self.check_llm_consensus(kwargs.get("consensus", {})),
            self.check_sentiment(kwargs.get("analyst_results", [])),
            self.check_technical(kwargs.get("analyst_results", [])),
            self.check_edge(
                kwargs.get("p_up", 0.5), kwargs.get("market_price", 0.5)
            ),
            self.check_market_regime(**kwargs.get("regime_kwargs", {})),
            self.check_liquidity_limits(kwargs.get("risk_status", {})),
        ]
        all_passed = all(g.passed for g in gates)
        return {
            "trade_allowed": all_passed,
            "gates": {
                g.gate_name: {
                    "passed": g.passed,
                    "value": g.value,
                    "reason": g.reason,
                }
                for g in gates
            },
            "passed_count": sum(1 for g in gates if g.passed),
            "total_gates": len(gates),
        }
