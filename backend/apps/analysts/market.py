from .base import BaseAnalyst, AnalystResult
import pandas as pd
import numpy as np
from data.models import Timeframe


class MarketAnalyst(BaseAnalyst):
    def __init__(self, llm_client=None, data_manager=None):
        self.llm_client = llm_client
        self.data_manager = data_manager
        self.indicators = ['RSI', 'MACD', 'BB', 'ATR', 'Stochastic', 'Ichimoku', 'Fibonacci', 'VWAP']

    async def analyze(self, symbol: str, timeframe: str) -> AnalystResult:
        if self.llm_client:
            from .prompts import build_prompt, parse_llm_response
            prompt = build_prompt('market', symbol, timeframe)
            response = self.llm_client.analyze(prompt)
            parsed = parse_llm_response(response.text, response.confidence)
            return AnalystResult(
                analyst_name='market',
                symbol=symbol,
                timeframe=timeframe,
                signal=parsed['signal'],
                confidence=parsed['confidence'],
                reasoning=parsed['reasoning'],
                data={'llm_model': response.model_used, 'indicators': self.indicators, 'data_source': 'llm'}
            )

        data = await self._fetch_market_data(symbol, timeframe)

        signals = []

        # RSI Analysis
        rsi = self._calculate_rsi(data['close'])
        if rsi < 30:
            signals.append(('BUY', 0.7))
        elif rsi > 70:
            signals.append(('SELL', 0.7))
        else:
            signals.append(('HOLD', 0.5))

        # MACD Analysis
        macd_signal = self._calculate_macd(data['close'])
        signals.append(macd_signal)

        # Bollinger Bands
        bb_signal = self._calculate_bollinger(data['close'])
        signals.append(bb_signal)

        # Aggregate signals
        buy_votes = sum(1 for s, _ in signals if s == 'BUY')
        sell_votes = sum(1 for s, _ in signals if s == 'SELL')

        if buy_votes > sell_votes:
            signal = 'BUY'
            confidence = sum(c for s, c in signals if s == 'BUY') / buy_votes if buy_votes > 0 else 0.5
        elif sell_votes > buy_votes:
            signal = 'SELL'
            confidence = sum(c for s, c in signals if s == 'SELL') / sell_votes if sell_votes > 0 else 0.5
        else:
            signal = 'HOLD'
            confidence = 0.5

        data_source = 'pipeline' if self.data_manager is not None else 'placeholder'

        return AnalystResult(
            analyst_name='market',
            symbol=symbol,
            timeframe=timeframe,
            signal=signal,
            confidence=min(confidence, 1.0),
            reasoning=f'RSI: {rsi:.1f}, MACD: {macd_signal[0]}, BB: {bb_signal[0]}',
            data={'rsi': rsi, 'macd': macd_signal, 'bb': bb_signal, 'indicators': self.indicators, 'data_source': data_source}
        )

    async def _fetch_market_data(self, symbol: str, timeframe: str) -> dict:
        if self.data_manager is not None:
            tf = Timeframe(timeframe)
            candles = await self.data_manager.get_candles(symbol, tf, 200)
            return {
                'close': pd.Series([c.close for c in candles]),
                'high': pd.Series([c.high for c in candles]),
                'low': pd.Series([c.low for c in candles]),
                'volume': pd.Series([c.volume for c in candles]),
            }
        return {
            'close': pd.Series(np.random.randn(100).cumsum() + 100),
            'high': pd.Series(np.random.randn(100).cumsum() + 101),
            'low': pd.Series(np.random.randn(100).cumsum() + 99),
            'volume': pd.Series(np.random.randint(1000, 10000, 100))
        }

    def _calculate_rsi(self, prices: pd.Series, period: int = 14) -> float:
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50.0

    def _calculate_macd(self, prices: pd.Series) -> tuple:
        ema12 = prices.ewm(span=12).mean()
        ema26 = prices.ewm(span=26).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9).mean()

        if macd.iloc[-1] > signal.iloc[-1]:
            return ('BUY', 0.65)
        elif macd.iloc[-1] < signal.iloc[-1]:
            return ('SELL', 0.65)
        return ('HOLD', 0.5)

    def _calculate_bollinger(self, prices: pd.Series, period: int = 20) -> tuple:
        sma = prices.rolling(window=period).mean()
        std = prices.rolling(window=period).std()
        upper = sma + (std * 2)
        lower = sma - (std * 2)

        current = prices.iloc[-1]
        if current < lower.iloc[-1]:
            return ('BUY', 0.7)
        elif current > upper.iloc[-1]:
            return ('SELL', 0.7)
        return ('HOLD', 0.5)

    def get_capabilities(self) -> list[str]:
        return list(self.indicators)
