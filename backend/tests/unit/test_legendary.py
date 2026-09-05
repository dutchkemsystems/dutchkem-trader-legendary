import pytest
import pandas as pd
import numpy as np
from apps.legendary.seykota import SeykotaTrendModule
from apps.legendary.pyramiding import PyramidingLogic
from apps.legendary.turtle_soup import TurtleSoupModule

def test_seykota_trend_module():
    module = SeykotaTrendModule()
    assert hasattr(module, 'analyze_trend')
    assert module.adx_threshold == 20

def test_pyramiding_logic():
    module = PyramidingLogic()
    assert hasattr(module, 'should_add_position')
    assert module.max_entries == 4

def test_turtle_soup_module():
    module = TurtleSoupModule()
    assert hasattr(module, 'detect_false_breakout')
    assert module.lookback == 20

def test_seykota_analyze():
    module = SeykotaTrendModule()
    data = pd.DataFrame({
        'close': np.random.randn(200).cumsum() + 100,
        'high': np.random.randn(200).cumsum() + 101,
        'low': np.random.randn(200).cumsum() + 99
    })
    result = module.analyze_trend(data)
    assert 'trend' in result
    assert 'confidence' in result
    assert 'action' in result
    assert result['trend'] in ('BULLISH', 'BEARISH', 'NEUTRAL', 'CHOP')

def test_turtle_soup_detect():
    module = TurtleSoupModule()
    data = pd.DataFrame({
        'close': np.random.randn(50).cumsum() + 100,
        'high': np.random.randn(50).cumsum() + 101,
        'low': np.random.randn(50).cumsum() + 99
    })
    result = module.detect_false_breakout(data)
    # Result can be None or a dict with signal, confidence, reason
    if result is not None:
        assert 'signal' in result
        assert result['signal'] in ('BUY', 'SELL')

def test_pyramiding_should_add():
    module = PyramidingLogic()
    position = {'profit_pips': 30, 'action': 'BUY', 'lot_size': 0.1}
    data = pd.DataFrame({
        'close': np.random.randn(200).cumsum() + 100,
        'high': np.random.randn(200).cumsum() + 101,
        'low': np.random.randn(200).cumsum() + 99
    })
    result = module.should_add_position(position, data)
    if result is not None:
        assert 'add' in result
        assert 'additional_lot' in result
        assert 'reason' in result

def test_pyramiding_max_entries():
    module = PyramidingLogic()
    module.entry_count = 4
    position = {'profit_pips': 30, 'action': 'BUY', 'lot_size': 0.1}
    data = pd.DataFrame({
        'close': np.random.randn(200).cumsum() + 100,
        'high': np.random.randn(200).cumsum() + 101,
        'low': np.random.randn(200).cumsum() + 99
    })
    result = module.should_add_position(position, data)
    assert result is None

def test_seykota_blocks_chop():
    module = SeykotaTrendModule()
    data = pd.DataFrame({
        'close': np.ones(200) * 100 + np.random.randn(200) * 0.1,
        'high': np.ones(200) * 100.1 + np.random.randn(200) * 0.1,
        'low': np.ones(200) * 99.9 + np.random.randn(200) * 0.1
    })
    result = module.analyze_trend(data)
    assert result['trend'] == 'CHOP'
    assert result['action'] == 'HOLD'
