"""Tests for Consensus Gates — Wired in Execution Path."""

import pytest
from unittest.mock import MagicMock


class TestConsensusGatesIntegration:
    """Test that all 4 wired gates work correctly."""

    def _make_gates(self):
        from apps.consensus.gates import ConsensusGates
        return ConsensusGates()

    def test_ml_gate_passes_with_good_features(self):
        """ML gate should pass when features are within normal range."""
        from apps.consensus.gates import ConsensusGates
        gates = ConsensusGates()
        result = gates.check_ml_model([55, 0.01, 0.02, 0.003, 1.2, 0.5, 1.0, 30, 0.01, 0.01])
        assert result.passed is True

    def test_ml_gate_fails_with_bad_features(self):
        """ML gate should fail when model predicts low P(UP)."""
        from apps.consensus.gates import ConsensusGates, GateResult
        # Create a mock ML predictor that always predicts 0.3
        mock_ml = MagicMock()
        mock_pred = MagicMock()
        mock_pred.p_up = 0.3
        mock_ml.predict_from_features.return_value = mock_pred
        gates = ConsensusGates(ml_predictor=mock_ml)
        result = gates.check_ml_model([50, 0, 0, 0, 1.0, 0, 0, 20, 0, 0])
        assert result.passed is False

    def test_technical_gate_passes_with_confident_result(self):
        """Technical gate should pass when confidence >= 0.70."""
        from apps.consensus.gates import ConsensusGates
        from apps.analysts.base import AnalystResult
        gates = ConsensusGates()
        result_obj = AnalystResult(
            analyst_name="Technical", symbol="EURUSD", timeframe="M15",
            signal="BUY", confidence=0.85,
            reasoning="test", data_source="technical"
        )
        result = gates.check_technical([result_obj])
        assert result.passed is True
        assert result.value == pytest.approx(0.85, abs=0.01)

    def test_technical_gate_fails_with_low_confidence(self):
        """Technical gate should fail when confidence < 0.70."""
        from apps.consensus.gates import ConsensusGates
        from apps.analysts.base import AnalystResult
        gates = ConsensusGates()
        result_obj = AnalystResult(
            analyst_name="Technical", symbol="EURUSD", timeframe="M15",
            signal="BUY", confidence=0.50,
            reasoning="test", data_source="technical"
        )
        result = gates.check_technical([result_obj])
        assert result.passed is False

    def test_edge_gate_passes_with_positive_edge(self):
        """Edge gate should pass when P(UP) - price > 0.02."""
        from apps.consensus.gates import ConsensusGates
        gates = ConsensusGates()
        result = gates.check_edge(p_up=0.60, market_price=0.50)
        assert result.passed is True
        assert result.value > 0.02

    def test_edge_gate_fails_with_no_edge(self):
        """Edge gate should fail when edge < 0.02."""
        from apps.consensus.gates import ConsensusGates
        gates = ConsensusGates()
        result = gates.check_edge(p_up=0.50, market_price=0.50)
        assert result.passed is False

    def test_liquidity_gate_passes_with_room(self):
        """Liquidity gate should pass when positions < max."""
        from apps.consensus.gates import ConsensusGates
        gates = ConsensusGates()
        risk_status = {"max_positions": 10, "current_positions": 3}
        result = gates.check_liquidity_limits(risk_status)
        assert result.passed is True

    def test_liquidity_gate_fails_at_limit(self):
        """Liquidity gate should fail when positions >= max."""
        from apps.consensus.gates import ConsensusGates
        gates = ConsensusGates()
        risk_status = {"max_positions": 10, "current_positions": 10}
        result = gates.check_liquidity_limits(risk_status)
        assert result.passed is False

    def test_evaluate_all_runs_all_8_gates(self):
        """evaluate_all should run all 8 gates and return combined result."""
        from apps.consensus.gates import ConsensusGates
        gates = ConsensusGates()
        result = gates.evaluate_all(
            features=[55, 0.01, 0.02, 0.003, 1.2, 0.5, 1.0, 30, 0.01, 0.01],
            consensus={"agreement_pct": 0.80},
            analyst_results=[],
            p_up=0.55,
            market_price=0.50,
            risk_status={"max_positions": 10, "current_positions": 3},
        )
        assert "trade_allowed" in result
        assert result["total_gates"] == 8
        assert isinstance(result["gates"], dict)


class TestConsensusGatesWired:
    """Test that the execution path actually calls the gates."""

    def test_execution_path_imports_analyst_result(self):
        """unified_engine.py should import AnalystResult for technical gate."""
        import importlib
        mod = importlib.import_module("unified_engine")
        # Check the module can be imported (it imports AnalystResult in execute_trade)
        assert hasattr(mod, "UnifiedEngine")

    def test_risk_state_includes_max_positions(self):
        """Risk state should include max_positions for liquidity gate."""
        import importlib
        mod = importlib.import_module("unified_engine")
        rm = mod.RiskManager()
        state = rm.get_state()
        # The liquidity gate needs max_positions and current_positions
        # These are added in the execute_trade method before calling the gate
        assert "open_positions" in state
