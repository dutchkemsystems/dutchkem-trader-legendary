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
        if chart_data is None:
            return AnalystResult(
                analyst_name='technical',
                symbol=symbol,
                timeframe=timeframe,
                signal='HOLD',
                confidence=0.0,
                reasoning='MT5 data unavailable — cannot analyze',
                data={'error': 'MT5 unavailable', 'data_source': 'none'}
            )
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
        # Always try MT5 first for real data
        try:
            import MetaTrader5 as mt5
            import numpy as np
            tf_map = {
                'M1': mt5.TIMEFRAME_M1, 'M5': mt5.TIMEFRAME_M5, 'M15': mt5.TIMEFRAME_M15,
                'M30': mt5.TIMEFRAME_M30, 'H1': mt5.TIMEFRAME_H1, 'H4': mt5.TIMEFRAME_H4,
                'D1': mt5.TIMEFRAME_D1, 'W1': mt5.TIMEFRAME_W1, 'MN1': mt5.TIMEFRAME_MN1,
            }
            mt5_tf = tf_map.get(timeframe.upper(), mt5.TIMEFRAME_H1)
            rates = mt5.copy_rates_from_pos(symbol, mt5_tf, 0, 100)
            if rates is not None and len(rates) >= 20:
                closes = np.array([r['close'] for r in rates])
                highs = np.array([r['high'] for r in rates])
                lows = np.array([r['low'] for r in rates])
                patterns = []
                rsi = self._calc_rsi_np(closes)
                macd_val = self._calc_macd_np(closes)
                sma20 = np.mean(closes[-20:])
                sma50 = np.mean(closes[-50:]) if len(closes) >= 50 else sma20
                support = float(np.min(lows[-20:]))
                resistance = float(np.max(highs[-20:]))
                if closes[-1] > sma20 > sma50:
                    patterns.append('bullish_trend')
                elif closes[-1] < sma20 < sma50:
                    patterns.append('bearish_trend')
                if rsi < 30:
                    patterns.append('oversold_bounce')
                elif rsi > 70:
                    patterns.append('overbought_reversal')
                if macd_val > 0 and len(closes) > 2:
                    prev_macd = self._calc_macd_np(closes[:-1])
                    if prev_macd <= 0:
                        patterns.append('bullish_crossover')
                elif macd_val < 0 and len(closes) > 2:
                    prev_macd = self._calc_macd_np(closes[:-1])
                    if prev_macd >= 0:
                        patterns.append('bearish_crossover')
                if len(highs) >= 5:
                    recent_highs = highs[-5:]
                    if all(recent_highs[i] >= recent_highs[i+1] for i in range(len(recent_highs)-1)):
                        patterns.append('double_top') if highs[-1] > highs[-3] * 0.999 else None
                    recent_lows = lows[-5:]
                    if all(recent_lows[i] <= recent_lows[i+1] for i in range(len(recent_lows)-1)):
                        patterns.append('double_bottom') if lows[-1] < lows[-3] * 1.001 else None
                if not patterns:
                    patterns.append('no_clear_pattern')
                trend = 'up' if closes[-1] > sma20 else 'down' if closes[-1] < sma20 else 'neutral'
                return {'patterns': patterns, 'trend': trend, 'support': support, 'resistance': resistance}
        except Exception:
            pass
        return None  # No MT5 data available

    def _calc_rsi_np(self, closes, period=14):
        import numpy as np
        deltas = np.diff(closes[-period-1:], prepend=closes[-period-1])
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return float(100 - (100 / (1 + rs)))

    def _calc_macd_np(self, closes):
        import numpy as np
        prices = np.array(closes, dtype=float)
        ema12 = self._ema_np(prices, 12)
        ema26 = self._ema_np(prices, 26)
        macd_line = ema12 - ema26
        return float(macd_line[-1])

    def _ema_np(self, data, span):
        import numpy as np
        alpha = 2 / (span + 1)
        ema = np.zeros_like(data, dtype=float)
        ema[0] = data[0]
        for i in range(1, len(data)):
            ema[i] = alpha * data[i] + (1 - alpha) * ema[i-1]
        return ema

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
