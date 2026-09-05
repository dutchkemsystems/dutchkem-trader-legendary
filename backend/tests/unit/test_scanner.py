import pytest
import asyncio
from apps.scanner.scanner import MultiTimeframeScanner, ScanResult, TimeframeResult


def test_scanner_creation():
    scanner = MultiTimeframeScanner()
    assert hasattr(scanner, 'scan')
    assert scanner.timeframes == ['1M', '5M', '15M', '1H', '4H', 'Daily']


def test_bias_filtering():
    scanner = MultiTimeframeScanner()
    assert '1H' in scanner.timeframes


def test_scanner_scan():
    scanner = MultiTimeframeScanner()
    result = asyncio.run(scanner.scan('EURUSD'))
    assert result.symbol == 'EURUSD'
    assert result.overall_signal in ('BUY', 'SELL', 'HOLD')
    assert 0.0 <= result.overall_confidence <= 1.0
    assert result.h1_bias in ('BUY', 'SELL', 'HOLD')
