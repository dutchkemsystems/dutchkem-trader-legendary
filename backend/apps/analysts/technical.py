import random

from .base import BaseAnalyst, AnalystResult


class TechnicalAnalyst(BaseAnalyst):
    def __init__(self, llm_client=None, chart_analyzer=None):
        self.llm_client = llm_client
        self.chart_analyzer = chart_analyzer
        self._capabilities = ['chart_patterns', 'support_resistance', 'trendlines', 'candlestick_patterns']

    async def analyze(self, symbol: str, timeframe: str) -> AnalystResult:
        if self.llm_client:
            from .prompts import build_prompt, parse_llm_response
            prompt = build_prompt('technical', symbol, timeframe)
            response = self.llm_client.analyze(prompt)
            parsed = parse_llm_response(response.text, response.confidence)
            return AnalystResult(
                analyst_name='technical',
                symbol=symbol,
                timeframe=timeframe,
                signal=parsed['signal'],
                confidence=parsed['confidence'],
                reasoning=parsed['reasoning'],
                data={'llm_model': response.model_used, 'data_source': 'llm'}
            )

        chart_data = await self._fetch_chart_data(symbol, timeframe)
        patterns = self._detect_patterns(chart_data)
        sr_levels = self._find_support_resistance(chart_data)

        signal, confidence = self._evaluate_patterns(patterns, sr_levels)

        return AnalystResult(
            analyst_name='technical',
            symbol=symbol,
            timeframe=timeframe,
            signal=signal,
            confidence=confidence,
            reasoning=f'Patterns: {", ".join(patterns)}, S/R: {sr_levels}',
            data={'patterns': patterns, 'support': sr_levels['support'],
                  'resistance': sr_levels['resistance']}
        )

    async def _fetch_chart_data(self, symbol: str, timeframe: str) -> dict:
        if self.chart_analyzer:
            base_price = 1.10
            candles = [
                {
                    'open': base_price + random.uniform(-0.01, 0.01),
                    'high': base_price + random.uniform(0, 0.02),
                    'low': base_price - random.uniform(0, 0.02),
                    'close': base_price + random.uniform(-0.01, 0.01)
                }
                for _ in range(20)
            ]
            analysis = self.chart_analyzer.score_chart(symbol, candles)
            return {
                'patterns': [p.name for p in analysis.patterns],
                'trend': 'up' if analysis.signal == 'BUY' else 'down' if analysis.signal == 'SELL' else 'neutral',
                'support': analysis.support_levels[0] if analysis.support_levels else 1.085,
                'resistance': analysis.resistance_levels[0] if analysis.resistance_levels else 1.115
            }
        return {'patterns': ['double_bottom', 'bullish_engulfing'], 'trend': 'up',
                'support': 1.085, 'resistance': 1.105}

    def _detect_patterns(self, chart_data: dict) -> list:
        return chart_data.get('patterns', [])

    def _find_support_resistance(self, chart_data: dict) -> dict:
        return {'support': chart_data.get('support', 1.085),
                'resistance': chart_data.get('resistance', 1.105)}

    def _evaluate_patterns(self, patterns: list, sr_levels: dict) -> tuple:
        bullish_patterns = ['double_bottom', 'bullish_engulfing', 'hammer', 'morning_star']
        bearish_patterns = ['double_top', 'bearish_engulfing', 'shooting_star', 'evening_star']

        bull_count = sum(1 for p in patterns if p in bullish_patterns)
        bear_count = sum(1 for p in patterns if p in bearish_patterns)

        if bull_count > bear_count:
            return ('BUY', min(0.6 + bull_count * 0.1, 0.9))
        elif bear_count > bull_count:
            return ('SELL', min(0.6 + bear_count * 0.1, 0.9))
        return ('HOLD', 0.5)

    def get_capabilities(self) -> list[str]:
        return list(self._capabilities)
