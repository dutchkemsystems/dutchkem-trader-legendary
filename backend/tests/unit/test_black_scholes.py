import pytest
import math
from apps.consensus.black_scholes import BlackScholesEngine, EdgeResult

def test_d2_calculation():
    engine = BlackScholesEngine()
    d2 = engine.calculate_d2(
        stock_price=1.1000,
        strike_price=1.1000,
        risk_free_rate=0.05,
        volatility=0.15,
        time_to_expiry=30/365
    )
    assert isinstance(d2, float)
    assert -5 < d2 < 5

def test_p_up_calculation():
    engine = BlackScholesEngine()
    p_up = engine.calculate_p_up(
        stock_price=1.1000,
        strike_price=1.1000,
        risk_free_rate=0.05,
        volatility=0.15,
        time_to_expiry=30/365
    )
    assert 0.0 <= p_up <= 1.0

def test_momentum_adjustment():
    engine = BlackScholesEngine()
    p_base = 0.55
    p_adjusted = engine.apply_momentum_adjustment(p_base, momentum=0.8, weight=0.1)
    assert 0.0 <= p_adjusted <= 1.0
    assert p_adjusted != p_base

def test_edge_calculation():
    engine = BlackScholesEngine()
    edge = engine.calculate_edge(p_up=0.65, market_price=0.55)
    assert abs(edge - 0.10) < 0.001

def test_is_tradeable():
    engine = BlackScholesEngine()
    assert engine.is_tradeable(0.05, min_edge=0.02) is True
    assert engine.is_tradeable(0.01, min_edge=0.02) is False

def test_evaluate():
    engine = BlackScholesEngine()
    result = engine.evaluate(
        stock_price=1.1000,
        strike_price=1.1000,
        market_price=0.55,
        momentum=0.5
    )
    assert isinstance(result, EdgeResult)
    assert 0.0 <= result.p_up <= 1.0
    assert result.tradeable in (True, False)
