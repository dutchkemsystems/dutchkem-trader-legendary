"""Tests for Gold Hedge EA and basket management."""

import pytest
from decimal import Decimal
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

from apps.hedging.hedge_basket import HedgeBasketManager, BasketState, HedgeLevel
from apps.hedging.gold_hedge_ea import GoldHedgeEA, GoldHedgeIntegration


@pytest.fixture
def basket_config():
    """Default basket configuration."""
    return {
        'lot_progression': [0.01, 0.02, 0.03, 0.05, 0.08],
        'max_hedge_levels': 5,
        'basket_tp_usd': 50.0,
        'min_profit_floor_usd': 10.0,
        'freeze_loss_usd': 200.0,
        'trailing_tp_enabled': True,
        'trailing_tp_step_usd': 10.0,
    }


@pytest.fixture
def basket_manager(basket_config):
    """Create a HedgeBasketManager."""
    return HedgeBasketManager(basket_config)


@pytest.fixture
def gold_ea_config():
    """Gold Hedge EA configuration."""
    return {
        'symbol': 'XAUUSD',
        'htf': 'H4',
        'entry_tf': 'M5',
        'lot_progression': [0.01, 0.02, 0.03, 0.05, 0.08],
        'max_hedge_levels': 5,
        'basket_tp_usd': 50.0,
        'min_profit_floor_usd': 10.0,
        'freeze_loss_usd': 200.0,
        'trailing_tp_enabled': True,
        'trailing_tp_step_usd': 10.0,
        'hedge_distance_atr': 1.5,
        'ema_fast': 20,
        'ema_slow': 50,
        'rsi_period': 14,
        'atr_period': 14,
    }


class TestHedgeBasketManager:
    """Tests for HedgeBasketManager."""

    def test_create_basket(self, basket_manager):
        """Should create a new basket."""
        basket = basket_manager.create_basket('XAUUSD', 'BUY', 2000.0, 12345)
        assert basket is not None
        assert basket.symbol == 'XAUUSD'
        assert basket.current_level == 1
        assert basket.total_lots == 0.01
        assert basket.levels[0].direction == 'BUY'

    def test_has_active_basket(self, basket_manager):
        """Should detect active basket."""
        assert basket_manager.has_active_basket('XAUUSD') is False
        basket_manager.create_basket('XAUUSD', 'BUY', 2000.0, 12345)
        assert basket_manager.has_active_basket('XAUUSD') is True

    def test_add_hedge(self, basket_manager):
        """Should add hedge level with opposite direction."""
        basket_manager.create_basket('XAUUSD', 'BUY', 2000.0, 12345)
        hedge = basket_manager.add_hedge('XAUUSD', 2010.0, 12346)
        assert hedge is not None
        assert hedge.direction == 'SELL'
        assert hedge.lots == 0.02
        assert basket_manager.get_basket('XAUUSD').current_level == 2

    def test_add_hedge_max_levels(self, basket_manager):
        """Should not exceed max hedge levels."""
        basket_manager.create_basket('XAUUSD', 'BUY', 2000.0, 12345)
        for i in range(4):
            basket_manager.add_hedge('XAUUSD', 2000.0 + i * 10, 12346 + i)
        
        # 5th level should fail (max is 5, already have 5)
        hedge = basket_manager.add_hedge('XAUUSD', 2050.0, 12350)
        assert hedge is None

    def test_add_hedge_frozen_basket(self, basket_manager):
        """Should not add hedge to frozen basket."""
        basket = basket_manager.create_basket('XAUUSD', 'BUY', 2000.0, 12345)
        basket.is_frozen = True
        hedge = basket_manager.add_hedge('XAUUSD', 2010.0, 12346)
        assert hedge is None

    def test_calculate_basket_pnl(self, basket_manager):
        """Should calculate combined P&L."""
        basket_manager.create_basket('XAUUSD', 'BUY', 2000.0, 12345)
        basket_manager.add_hedge('XAUUSD', 2010.0, 12346)
        
        pnl = basket_manager.calculate_basket_pnl('XAUUSD', {'bid': 2005.0, 'ask': 2005.0})
        # BUY @ 2000, SELL @ 2010, current = 2005
        # BUY PnL: (2005 - 2000) * 0.01 * 1.0 = 0.05
        # SELL PnL: (2010 - 2005) * 0.02 * 1.0 = 0.10
        # Total: 0.15
        assert pnl == pytest.approx(0.15, abs=0.01)

    def test_should_close_basket_tp(self, basket_manager):
        """Should close when profit hits take-profit."""
        basket_manager.create_basket('XAUUSD', 'BUY', 2000.0, 12345)
        should_close, reason = basket_manager.should_close_basket('XAUUSD', 55.0)
        assert should_close is True
        assert 'TP HIT' in reason

    def test_should_close_basket_freeze(self, basket_manager):
        """Should close when loss exceeds freeze threshold."""
        basket_manager.create_basket('XAUUSD', 'BUY', 2000.0, 12345)
        should_close, reason = basket_manager.should_close_basket('XAUUSD', -250.0)
        assert should_close is True
        assert 'FREEZE' in reason

    def test_should_not_close_small_loss(self, basket_manager):
        """Should not close for small losses."""
        basket_manager.create_basket('XAUUSD', 'BUY', 2000.0, 12345)
        should_close, reason = basket_manager.should_close_basket('XAUUSD', -5.0)
        assert should_close is False

    def test_close_basket(self, basket_manager):
        """Should close and remove basket."""
        basket_manager.create_basket('XAUUSD', 'BUY', 2000.0, 12345)
        closed = basket_manager.close_basket('XAUUSD')
        assert closed is not None
        assert closed.symbol == 'XAUUSD'
        assert basket_manager.has_active_basket('XAUUSD') is False

    def test_get_all_baskets(self, basket_manager):
        """Should return all active baskets."""
        basket_manager.create_basket('XAUUSD', 'BUY', 2000.0, 12345)
        basket_manager.create_basket('EURUSD', 'SELL', 1.1000, 12346)
        baskets = basket_manager.get_all_baskets()
        assert len(baskets) == 2
        assert 'XAUUSD' in baskets
        assert 'EURUSD' in baskets


class TestGoldHedgeEA:
    """Tests for GoldHedgeEA strategy."""

    def test_init(self, gold_ea_config):
        """Should initialize with config."""
        ea = GoldHedgeEA(gold_ea_config)
        assert ea.config == gold_ea_config
        assert ea.ema_fast == 20
        assert ea.ema_slow == 50

    def test_analyze_returns_none_for_non_xau(self, gold_ea_config):
        """Should return None for non-gold symbols."""
        import pandas as pd
        ea = GoldHedgeEA(gold_ea_config)
        data = pd.DataFrame({
            'open': [1.1] * 100,
            'high': [1.101] * 100,
            'low': [1.099] * 100,
            'close': [1.1] * 100,
            'volume': [100] * 100,
        })
        result = ea.analyze('EURUSD', data)
        assert result is None

    def test_analyze_returns_none_with_insufficient_data(self, gold_ea_config):
        """Should return None with insufficient data."""
        import pandas as pd
        ea = GoldHedgeEA(gold_ea_config)
        data = pd.DataFrame({
            'open': [2000.0] * 30,
            'high': [2001.0] * 30,
            'low': [1999.0] * 30,
            'close': [2000.0] * 30,
            'volume': [100] * 30,
        })
        result = ea.analyze('XAUUSD', data)
        assert result is None

    def test_get_trend_buy(self, gold_ea_config):
        """Should detect BUY trend."""
        ea = GoldHedgeEA(gold_ea_config)
        trend = ea._get_trend(2010.0, 2005.0, 2000.0)
        assert trend == 'BUY'

    def test_get_trend_sell(self, gold_ea_config):
        """Should detect SELL trend."""
        ea = GoldHedgeEA(gold_ea_config)
        trend = ea._get_trend(1990.0, 1995.0, 2000.0)
        assert trend == 'SELL'

    def test_get_trend_neutral(self, gold_ea_config):
        """Should detect NEUTRAL."""
        ea = GoldHedgeEA(gold_ea_config)
        trend = ea._get_trend(2000.0, 1995.0, 2005.0)
        assert trend == 'NEUTRAL'

    def test_calculate_rsi(self, gold_ea_config):
        """Should calculate RSI."""
        import pandas as pd
        import numpy as np
        ea = GoldHedgeEA(gold_ea_config)
        
        np.random.seed(42)
        prices = 2000.0 + np.cumsum(np.random.randn(50) * 2)
        close = pd.Series(prices)
        rsi = ea._calculate_rsi(close, 14)
        
        assert len(rsi) == 50
        assert rsi.iloc[-1] >= 0
        assert rsi.iloc[-1] <= 100

    def test_calculate_atr(self, gold_ea_config):
        """Should calculate ATR."""
        import pandas as pd
        import numpy as np
        ea = GoldHedgeEA(gold_ea_config)
        
        np.random.seed(42)
        n = 50
        data = pd.DataFrame({
            'open': 2000.0 + np.cumsum(np.random.randn(n)),
            'high': 2001.0 + np.cumsum(np.random.randn(n)),
            'low': 1999.0 + np.cumsum(np.random.randn(n)),
            'close': 2000.0 + np.cumsum(np.random.randn(n)),
            'volume': np.random.randint(100, 1000, n),
        })
        atr = ea._calculate_atr(data, 14)
        
        assert len(atr) == n
        assert atr.iloc[-1] > 0

    def test_get_status_inactive(self, gold_ea_config):
        """Should return inactive status."""
        ea = GoldHedgeEA(gold_ea_config)
        status = ea.get_status()
        assert status['active'] is False
        assert status['levels'] == 0

    def test_get_status_active(self, gold_ea_config):
        """Should return active status with basket."""
        ea = GoldHedgeEA(gold_ea_config)
        ea.basket_manager.create_basket('XAUUSD', 'BUY', 2000.0, 12345)
        status = ea.get_status()
        assert status['active'] is True
        assert status['levels'] == 1
        assert status['total_lots'] == 0.01


class TestGoldHedgeIntegration:
    """Tests for GoldHedgeIntegration."""

    def test_init(self, gold_ea_config):
        """Should initialize integration."""
        mock_mt5 = MagicMock()
        integration = GoldHedgeIntegration(gold_ea_config, mock_mt5)
        assert integration.enabled is False  # default disabled

    def test_tick_disabled(self, gold_ea_config):
        """Should not execute when disabled."""
        mock_mt5 = MagicMock()
        integration = GoldHedgeIntegration(gold_ea_config, mock_mt5)
        integration.tick()  # Should not raise
        mock_mt5.place_order.assert_not_called()

    def test_get_status(self, gold_ea_config):
        """Should return status dict."""
        mock_mt5 = MagicMock()
        integration = GoldHedgeIntegration(gold_ea_config, mock_mt5)
        status = integration.get_status()
        assert 'active' in status
        assert 'symbol' in status
