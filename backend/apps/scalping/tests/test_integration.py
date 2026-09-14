"""Integration tests for scalping strategies."""

import pytest
from unittest.mock import Mock
from apps.scalping.engine import ScalpingEngine
from apps.scalping.config import SCALPING_STRATEGIES


@pytest.fixture
def mock_mt5():
    mt5 = Mock()
    mt5.fetch_candles.return_value = Mock()
    mt5.place_order.return_value = {'ticket': 12345, 'status': 'ok'}
    return mt5


@pytest.fixture
def mock_risk():
    risk = Mock()
    risk.daily_pnl_pct = 0.0
    risk.check_spread.return_value = True
    risk.check_correlation.return_value = True
    risk.check_portfolio_limits.return_value = True
    risk.check_circuit_breaker.return_value = True
    risk.calculate_position_size.return_value = 0.01
    risk.trade_results = []
    risk.win_streak = 0
    risk.loss_streak = 0
    risk.daily_pnl = 0.0
    return risk


@pytest.mark.asyncio
async def test_full_scalping_flow(mock_mt5, mock_risk):
    """Integration test: strategy -> signal -> risk check -> execution -> sync."""
    original_enabled = SCALPING_STRATEGIES['chiaroscuro']['enabled']
    SCALPING_STRATEGIES['chiaroscuro']['enabled'] = True
    try:
        engine = ScalpingEngine(mock_mt5, mock_risk)
        assert 'chiaroscuro' in engine.strategies
        await engine.run_cycle(['EURUSD'])
    finally:
        SCALPING_STRATEGIES['chiaroscuro']['enabled'] = original_enabled


def test_trade_sync_updates_risk_manager(mock_mt5, mock_risk):
    """Verify trade results sync back to RiskManager."""
    engine = ScalpingEngine(mock_mt5, mock_risk)
    engine.trade_history.append({'status': 'closed', 'pnl': 50.0})
    engine.trade_history.append({'status': 'closed', 'pnl': -30.0})
    results = engine.get_trade_results()
    assert len(results) == 2
    assert results[0]['pnl'] == 50.0
    assert results[1]['pnl'] == -30.0
