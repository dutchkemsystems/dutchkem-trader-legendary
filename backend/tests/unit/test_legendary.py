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
