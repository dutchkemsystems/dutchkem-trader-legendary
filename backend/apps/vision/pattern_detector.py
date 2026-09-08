from dataclasses import dataclass
from typing import List, Dict


@dataclass
class CandlestickPattern:
    name: str
    signal: str  # "bullish", "bearish", "neutral"
    confidence: float


class PatternDetector:
    def detect_from_candles(self, candles: List[Dict]) -> List[CandlestickPattern]:
        patterns = []
        if len(candles) < 3:
            return patterns

        for i in range(2, len(candles)):
            prev = candles[i - 2]
            curr = candles[i - 1]
            next_ = candles[i]

            # Doji detection
            body = abs(curr['close'] - curr['open'])
            range_ = curr['high'] - curr['low']
            if range_ > 0 and body / range_ < 0.1:
                patterns.append(CandlestickPattern("doji", "neutral", 0.6))

            # Bullish engulfing
            if (curr['close'] < curr['open']
                    and next_['close'] > next_['open']
                    and next_['close'] > curr['open']
                    and next_['open'] < curr['close']):
                patterns.append(CandlestickPattern("bullish_engulfing", "bullish", 0.75))

            # Bearish engulfing
            if (curr['close'] > curr['open']
                    and next_['close'] < next_['open']
                    and next_['close'] < curr['open']
                    and next_['open'] > curr['close']):
                patterns.append(CandlestickPattern("bearish_engulfing", "bearish", 0.75))

            # Hammer (bullish reversal)
            body = abs(curr['close'] - curr['open'])
            lower_shadow = min(curr['open'], curr['close']) - curr['low']
            upper_shadow = curr['high'] - max(curr['open'], curr['close'])
            if lower_shadow > body * 2 and upper_shadow < body * 0.5:
                patterns.append(CandlestickPattern("hammer", "bullish", 0.7))

        return patterns
