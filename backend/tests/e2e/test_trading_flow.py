# backend/tests/e2e/test_trading_flow.py
import pytest
import asyncio
import pandas as pd
import numpy as np
from apps.analysts.market import MarketAnalyst
from apps.analysts.news import NewsAnalyst
from apps.consensus.engine import ConsensusEngine
from apps.scanner.scanner import MultiTimeframeScanner
from apps.legendary.seykota import SeykotaTrendModule
from apps.legendary.turtle_soup import TurtleSoupModule

@pytest.mark.asyncio
async def test_full_trading_flow():
    # 1. Initialize components
    analysts = [MarketAnalyst(), NewsAnalyst()]
    engine = ConsensusEngine(analysts=analysts)
    scanner = MultiTimeframeScanner()
    seykota = SeykotaTrendModule()
    turtle = TurtleSoupModule()
    
    symbol = "EURUSD"
    
    # 2. Run multi-timeframe scan
    scan_result = await scanner.scan(symbol)
    assert scan_result.symbol == symbol
    assert scan_result.overall_signal in ['BUY', 'SELL', 'HOLD']
    
    # 3. Run consensus evaluation
    consensus_result = await engine.evaluate(symbol, "1H")
    assert consensus_result['action'] in ['BUY', 'SELL', 'HOLD']
    assert 0 <= consensus_result['confidence'] <= 1
    
    # 4. Run legendary modules
    data = pd.DataFrame({
        'close': np.random.randn(200).cumsum() + 100,
        'high': np.random.randn(200).cumsum() + 101,
        'low': np.random.randn(200).cumsum() + 99
    })
    
    seykota_result = seykota.analyze_trend(data)
    assert seykota_result['trend'] in ['BULLISH', 'BEARISH', 'NEUTRAL', 'CHOP']
    
    turtle_result = turtle.detect_false_breakout(data)
    assert turtle_result is None or isinstance(turtle_result, dict)

