import pytest
import tempfile
import os
import numpy as np
import cv2
from apps.vision.chart_analyzer import ChartAnalyzer, ChartAnalysis
from apps.vision.pattern_detector import PatternDetector, CandlestickPattern
from apps.vision.chart_image_analyzer import ChartImageAnalyzer, ImageAnalysis, TrendLine


def test_chart_analyzer_initializes():
    analyzer = ChartAnalyzer()
    assert analyzer is not None


def test_pattern_detector_initializes():
    detector = PatternDetector()
    assert detector is not None


def test_detect_candlestick_patterns():
    detector = PatternDetector()
    candles = [
        {'open': 1.10, 'high': 1.12, 'low': 1.09, 'close': 1.11},
        {'open': 1.11, 'high': 1.13, 'low': 1.10, 'close': 1.09},
        {'open': 1.09, 'high': 1.12, 'low': 1.08, 'close': 1.115},
    ]
    patterns = detector.detect_from_candles(candles)
    assert isinstance(patterns, list)


def test_detect_doji_pattern():
    detector = PatternDetector()
    candles = [
        {'open': 1.10, 'high': 1.12, 'low': 1.08, 'close': 1.10},
        {'open': 1.10, 'high': 1.11, 'low': 1.09, 'close': 1.101},
        {'open': 1.101, 'high': 1.12, 'low': 1.09, 'close': 1.11},
    ]
    patterns = detector.detect_from_candles(candles)
    doji_found = any(p.name == "doji" for p in patterns)
    assert doji_found, "Should detect doji when body/range < 0.1"


def test_detect_bullish_engulfing():
    detector = PatternDetector()
    candles = [
        {'open': 1.10, 'high': 1.11, 'low': 1.09, 'close': 1.105},
        {'open': 1.10, 'high': 1.105, 'low': 1.085, 'close': 1.085},
        {'open': 1.08, 'high': 1.11, 'low': 1.075, 'close': 1.105},
    ]
    patterns = detector.detect_from_candles(candles)
    engulfing = [p for p in patterns if p.name == "bullish_engulfing"]
    assert len(engulfing) > 0, "Should detect bullish engulfing pattern"


def test_detect_bearish_engulfing():
    detector = PatternDetector()
    candles = [
        {'open': 1.08, 'high': 1.09, 'low': 1.07, 'close': 1.085},
        {'open': 1.085, 'high': 1.10, 'low': 1.08, 'close': 1.095},
        {'open': 1.10, 'high': 1.105, 'low': 1.08, 'close': 1.082},
    ]
    patterns = detector.detect_from_candles(candles)
    engulfing = [p for p in patterns if p.name == "bearish_engulfing"]
    assert len(engulfing) > 0, "Should detect bearish engulfing pattern"


def test_detect_hammer():
    detector = PatternDetector()
    candles = [
        {'open': 1.10, 'high': 1.11, 'low': 1.09, 'close': 1.105},
        {'open': 1.10, 'high': 1.1005, 'low': 1.07, 'close': 1.098},
        {'open': 1.098, 'high': 1.11, 'low': 1.09, 'close': 1.105},
    ]
    patterns = detector.detect_from_candles(candles)
    hammer_found = any(p.name == "hammer" for p in patterns)
    assert hammer_found, "Should detect hammer pattern"


def test_insufficient_candles_returns_empty():
    detector = PatternDetector()
    candles = [
        {'open': 1.10, 'high': 1.12, 'low': 1.09, 'close': 1.11},
    ]
    patterns = detector.detect_from_candles(candles)
    assert len(patterns) == 0


def test_score_chart():
    analyzer = ChartAnalyzer()
    candles = [
        {'open': 1.10 + i * 0.001, 'high': 1.11 + i * 0.001, 'low': 1.09 + i * 0.001, 'close': 1.105 + i * 0.001}
        for i in range(10)
    ]
    result = analyzer.score_chart("EURUSD", candles)
    assert isinstance(result, ChartAnalysis)
    assert result.signal in ("BUY", "SELL", "HOLD")
    assert 0.0 <= result.confidence <= 1.0


def test_score_chart_insufficient_data():
    analyzer = ChartAnalyzer()
    result = analyzer.score_chart("EURUSD", [{'open': 1.0, 'high': 1.1, 'low': 0.9, 'close': 1.05}])
    assert result.signal == "HOLD"
    assert result.confidence == 0.5
    assert "Insufficient" in result.reasoning


def test_score_chart_empty_candles():
    analyzer = ChartAnalyzer()
    result = analyzer.score_chart("EURUSD", [])
    assert result.signal == "HOLD"
    assert result.confidence == 0.5


def test_support_resistance_levels():
    analyzer = ChartAnalyzer()
    candles = [
        {'open': 1.10 + i * 0.005, 'high': 1.12 + i * 0.005, 'low': 1.09 + i * 0.005, 'close': 1.11 + i * 0.005}
        for i in range(25)
    ]
    result = analyzer.score_chart("EURUSD", candles)
    assert len(result.support_levels) > 0
    assert len(result.resistance_levels) > 0
    assert result.support_levels[0] <= result.resistance_levels[0]


def test_chart_analysis_has_reasoning():
    analyzer = ChartAnalyzer()
    candles = [
        {'open': 1.10, 'high': 1.12, 'low': 1.08, 'close': 1.10},
        {'open': 1.10, 'high': 1.105, 'low': 1.095, 'close': 1.101},
        {'open': 1.101, 'high': 1.12, 'low': 1.09, 'close': 1.11},
        {'open': 1.11, 'high': 1.12, 'low': 1.10, 'close': 1.105},
        {'open': 1.105, 'high': 1.115, 'low': 1.095, 'close': 1.11},
    ]
    result = analyzer.score_chart("EURUSD", candles)
    assert isinstance(result.reasoning, str)
    assert len(result.reasoning) > 0


def test_pattern_confidence_range():
    detector = PatternDetector()
    candles = [
        {'open': 1.10, 'high': 1.12, 'low': 1.08, 'close': 1.10},
        {'open': 1.10, 'high': 1.11, 'low': 1.09, 'close': 1.101},
        {'open': 1.101, 'high': 1.12, 'low': 1.09, 'close': 1.11},
    ]
    patterns = detector.detect_from_candles(candles)
    for p in patterns:
        assert 0.0 <= p.confidence <= 1.0


def test_candlestick_pattern_dataclass():
    p = CandlestickPattern(name="doji", signal="neutral", confidence=0.6)
    assert p.name == "doji"
    assert p.signal == "neutral"
    assert p.confidence == 0.6


def _create_synthetic_chart(path: str, width: int = 800, height: int = 600):
    img = np.ones((height, width, 3), dtype=np.uint8) * 255
    for x in range(50, 750, 20):
        open_ = 300 + np.random.randint(-50, 50)
        close = open_ + np.random.randint(-40, 40)
        high = max(open_, close) + np.random.randint(5, 30)
        low = min(open_, close) - np.random.randint(5, 30)
        color = (0, 180, 0) if close >= open_ else (0, 0, 200)
        cv2.line(img, (x, high), (x, low), (0, 0, 0), 1)
        cv2.rectangle(img, (x - 7, min(open_, close)), (x + 7, max(open_, close)), color, -1)
    cv2.line(img, (50, 100), (750, 500), (255, 0, 0), 2)
    cv2.line(img, (50, 400), (750, 400), (0, 0, 0), 2)
    cv2.imwrite(path, img)


def test_chart_image_analyzer_initializes():
    analyzer = ChartImageAnalyzer()
    assert analyzer is not None


def test_chart_image_analyzer_invalid_path():
    analyzer = ChartImageAnalyzer()
    result = analyzer.analyze_chart_image("nonexistent_file.png")
    assert isinstance(result, ImageAnalysis)
    assert "Failed" in result.reasoning


def test_chart_image_analyzer_with_synthetic_chart():
    analyzer = ChartImageAnalyzer()
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        temp_path = f.name
    try:
        _create_synthetic_chart(temp_path)
        result = analyzer.analyze_chart_image(temp_path)
        assert isinstance(result, ImageAnalysis)
        assert isinstance(result.trend_lines, list)
        assert isinstance(result.edge_density, float)
        assert 0.0 <= result.edge_density <= 1.0
        assert isinstance(result.reasoning, str)
        assert len(result.reasoning) > 0
    finally:
        os.unlink(temp_path)


def test_chart_image_preprocess():
    analyzer = ChartImageAnalyzer()
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f_in:
        in_path = f_in.name
    out_path = in_path + ".enhanced.png"
    try:
        _create_synthetic_chart(in_path)
        success = analyzer.preprocess_image(in_path, out_path)
        assert success is True
        assert os.path.exists(out_path)
    finally:
        if os.path.exists(in_path):
            os.unlink(in_path)
        if os.path.exists(out_path):
            os.unlink(out_path)


def test_chart_image_preprocess_invalid():
    analyzer = ChartImageAnalyzer()
    success = analyzer.preprocess_image("nonexistent.png", "out.png")
    assert success is False


def test_trend_line_dataclass():
    tl = TrendLine(slope=0.5, intercept=100, start_point=(0, 100), end_point=(200, 200), strength=0.8)
    assert tl.slope == 0.5
    assert tl.strength == 0.8
