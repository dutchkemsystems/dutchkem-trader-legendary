from dataclasses import dataclass, field
from typing import List, Dict, Optional
from .pattern_detector import PatternDetector, CandlestickPattern


@dataclass
class ChartAnalysis:
    signal: str  # "BUY", "SELL", "HOLD"
    confidence: float
    patterns: List[CandlestickPattern]
    support_levels: List[float]
    resistance_levels: List[float]
    reasoning: str


class ChartAnalyzer:
    def __init__(self):
        self.pattern_detector = PatternDetector()

    def score_chart(self, symbol: str, candles: List[Dict]) -> ChartAnalysis:
        if not candles or len(candles) < 5:
            return ChartAnalysis(
                signal="HOLD",
                confidence=0.5,
                patterns=[],
                support_levels=[],
                resistance_levels=[],
                reasoning="Insufficient data for analysis",
            )

        # Detect patterns
        patterns = self.pattern_detector.detect_from_candles(candles)

        # Calculate support/resistance
        support = self._find_support(candles)
        resistance = self._find_resistance(candles)

        # Score based on patterns
        bullish_score = sum(p.confidence for p in patterns if p.signal == "bullish")
        bearish_score = sum(p.confidence for p in patterns if p.signal == "bearish")

        if bullish_score > bearish_score and bullish_score > 0.5:
            signal = "BUY"
            confidence = min(0.9, 0.5 + bullish_score * 0.1)
        elif bearish_score > bullish_score and bearish_score > 0.5:
            signal = "SELL"
            confidence = min(0.9, 0.5 + bearish_score * 0.1)
        else:
            signal = "HOLD"
            confidence = 0.5

        reasoning = (
            f"Found {len(patterns)} patterns. "
            f"Bullish: {bullish_score:.2f}, Bearish: {bearish_score:.2f}"
        )

        return ChartAnalysis(
            signal=signal,
            confidence=confidence,
            patterns=patterns,
            support_levels=support,
            resistance_levels=resistance,
            reasoning=reasoning,
        )

    def _find_support(self, candles: List[Dict]) -> List[float]:
        lows = [c['low'] for c in candles[-20:]]
        return [min(lows)] if lows else []

    def _find_resistance(self, candles: List[Dict]) -> List[float]:
        highs = [c['high'] for c in candles[-20:]]
        return [max(highs)] if highs else []
