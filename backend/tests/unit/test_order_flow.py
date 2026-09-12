"""Tests for OrderFlow Fix — Real Tick Volume Data."""

import pytest
from unittest.mock import MagicMock, patch
from apps.analysts.order_flow import OrderFlowAnalyst


class TestOrderFlowData:
    """Test OrderFlow uses real tick data, not fabricated volumes."""

    def test_no_fabricated_volume_formulas(self):
        """OrderFlow should not contain fabricated volume formulas."""
        from pathlib import Path
        order_flow_path = Path(__file__).parent.parent.parent / "apps" / "analysts" / "order_flow.py"
        content = order_flow_path.read_text(encoding="utf-8")
        # These are the old fabricated formulas — should NOT exist
        assert "15000 + int((tick.bid - 1.1) * 100000)" not in content
        assert "12000 + int((1.1 - tick.ask) * 100000)" not in content

    def test_uses_copy_ticks_from_pos(self):
        """OrderFlow should use mt5.copy_ticks_from_pos for real tick data."""
        from pathlib import Path
        order_flow_path = Path(__file__).parent.parent.parent / "apps" / "analysts" / "order_flow.py"
        content = order_flow_path.read_text(encoding="utf-8")
        assert "copy_ticks_from_pos" in content

    def test_classifies_ticks_by_direction(self):
        """OrderFlow should classify ticks as buyer/seller initiated."""
        from pathlib import Path
        order_flow_path = Path(__file__).parent.parent.parent / "apps" / "analysts" / "order_flow.py"
        content = order_flow_path.read_text(encoding="utf-8")
        assert "directions = np.diff(prices)" in content
        assert "buyer_mask" in content
        assert "seller_mask" in content

    def test_data_source_is_mt5(self):
        """OrderFlow should set data_source='mt5' when data is available."""
        from apps.analysts.base import AnalystResult
        # The analyze method should return AnalystResult with data_source='mt5'
        from pathlib import Path
        order_flow_path = Path(__file__).parent.parent.parent / "apps" / "analysts" / "order_flow.py"
        content = order_flow_path.read_text(encoding="utf-8")
        assert "data_source='mt5'" in content


class TestOrderFlowSignal:
    """Test OrderFlow signal generation."""

    def test_microprice_calculation(self):
        """Microprice should be volume-weighted average of bid/ask."""
        analyst = OrderFlowAnalyst()
        data = {
            'bid_volume': 600,
            'ask_volume': 400,
            'bid_price': 1.0850,
            'ask_price': 1.0852,
        }
        microprice = analyst._calculate_microprice(data)
        # Microprice should be closer to the side with more volume
        assert 1.0850 <= microprice <= 1.0852

    def test_imbalance_calculation(self):
        """Imbalance should be (bid_vol - ask_vol) / total."""
        analyst = OrderFlowAnalyst()
        data = {'bid_volume': 700, 'ask_volume': 300}
        imbalance = analyst._calculate_imbalance(data)
        assert imbalance == pytest.approx(0.4, abs=0.01)

    def test_buy_signal_on_positive_imbalance(self):
        """Should return BUY when imbalance > 0.2."""
        analyst = OrderFlowAnalyst()
        signal, confidence = analyst._evaluate_flow(1.0851, 0.3)
        assert signal == "BUY"
        assert confidence > 0.5

    def test_sell_signal_on_negative_imbalance(self):
        """Should return SELL when imbalance < -0.2."""
        analyst = OrderFlowAnalyst()
        signal, confidence = analyst._evaluate_flow(1.0851, -0.3)
        assert signal == "SELL"
        assert confidence > 0.5

    def test_hold_on_neutral_imbalance(self):
        """Should return HOLD when imbalance is between -0.2 and 0.2."""
        analyst = OrderFlowAnalyst()
        signal, confidence = analyst._evaluate_flow(1.0851, 0.0)
        assert signal == "HOLD"
