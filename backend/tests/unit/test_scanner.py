import pytest
import asyncio
from apps.scanner.scanner import MultiTimeframeScanner, ScanResult, TimeframeResult


def test_scanner_creation():
    scanner = MultiTimeframeScanner()
    assert hasattr(scanner, 'scan')
    assert scanner.timeframes == ['1M', '5M', '15M', '1H', '4H', '1D']


def test_bias_filtering():
    import random
    random.seed(42)  # Seed for reproducibility

    scanner = MultiTimeframeScanner()
    result = asyncio.run(scanner.scan('EURUSD'))

    # Verify h1_bias is set
    assert result.h1_bias in ('BUY', 'SELL', 'HOLD')

    # Verify shorter timeframes have reduced confidence when they disagree with 1H bias
    for tf in ['1M', '5M', '15M']:
        tf_result = result.timeframes[tf]
        # If signal disagrees with 1H bias, confidence should be <= 0.45 (0.9 * 0.5)
        if tf_result.signal != result.h1_bias:
            assert tf_result.confidence <= 0.45, f"{tf} confidence should be halved when disagreeing with 1H bias"


def test_scanner_scan():
    scanner = MultiTimeframeScanner()
    result = asyncio.run(scanner.scan('EURUSD'))
    assert result.symbol == 'EURUSD'
    assert result.overall_signal in ('BUY', 'SELL', 'HOLD')
    assert 0.0 <= result.overall_confidence <= 1.0
    assert result.h1_bias in ('BUY', 'SELL', 'HOLD')
