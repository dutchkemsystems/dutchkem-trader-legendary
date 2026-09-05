import asyncio
from typing import Dict, Any, List, Tuple
from dataclasses import dataclass


@dataclass
class TimeframeResult:
    timeframe: str
    signal: str
    confidence: float
    data: Dict[str, Any]


@dataclass
class ScanResult:
    symbol: str
    timeframes: Dict[str, TimeframeResult]
    h1_bias: str
    alignment: float
    overall_signal: str
    overall_confidence: float


class MultiTimeframeScanner:
    def __init__(self):
        self.timeframes = ['1M', '5M', '15M', '1H', '4H', 'Daily']

    async def scan(self, symbol: str) -> ScanResult:
        tasks = [self._analyze_timeframe(symbol, tf) for tf in self.timeframes]
        results = await asyncio.gather(*tasks)

        timeframe_results = {r.timeframe: r for r in results}

        h1_bias = timeframe_results['1H'].signal

        for tf in ['1M', '5M', '15M']:
            if timeframe_results[tf].signal != h1_bias:
                timeframe_results[tf] = TimeframeResult(
                    timeframe=tf,
                    signal=timeframe_results[tf].signal,
                    confidence=timeframe_results[tf].confidence * 0.5,
                    data=timeframe_results[tf].data
                )

        alignment = self._calculate_alignment(timeframe_results)
        overall_signal, overall_confidence = self._aggregate_signals(timeframe_results)

        return ScanResult(
            symbol=symbol,
            timeframes=timeframe_results,
            h1_bias=h1_bias,
            alignment=alignment,
            overall_signal=overall_signal,
            overall_confidence=overall_confidence
        )

    async def _analyze_timeframe(self, symbol: str, timeframe: str) -> TimeframeResult:
        import random
        signals = ['BUY', 'SELL', 'HOLD']
        return TimeframeResult(
            timeframe=timeframe,
            signal=random.choice(signals),
            confidence=random.uniform(0.5, 0.9),
            data={'symbol': symbol, 'timeframe': timeframe}
        )

    def _calculate_alignment(self, results: Dict[str, TimeframeResult]) -> float:
        signals = [r.signal for r in results.values()]
        buy_count = signals.count('BUY')
        sell_count = signals.count('SELL')
        total = len(signals)
        return max(buy_count, sell_count) / total if total > 0 else 0

    def _aggregate_signals(self, results: Dict[str, TimeframeResult]) -> Tuple[str, float]:
        weights = {'1M': 0.1, '5M': 0.15, '15M': 0.2, '1H': 0.25, '4H': 0.3, 'Daily': 0.35}
        total_weight = sum(weights.values())

        buy_score = sum(weights[tf] for tf, r in results.items() if r.signal == 'BUY') / total_weight
        sell_score = sum(weights[tf] for tf, r in results.items() if r.signal == 'SELL') / total_weight

        if buy_score > sell_score:
            return ('BUY', min(buy_score, 1.0))
        elif sell_score > buy_score:
            return ('SELL', min(sell_score, 1.0))
        return ('HOLD', 0.5)
