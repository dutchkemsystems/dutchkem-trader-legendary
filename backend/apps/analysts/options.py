from .base import BaseAnalyst, AnalystResult


class OptionsAnalyst(BaseAnalyst):
    def __init__(self, llm_client=None):
        self.llm_client = llm_client
        self._capabilities = ['implied_volatility', 'put_call_ratio', 'greeks', 'unusual_activity']

    async def analyze(self, symbol: str, timeframe: str) -> AnalystResult:
        if self.llm_client:
            from .prompts import build_prompt, parse_llm_response
            prompt = build_prompt('options', symbol, timeframe)
            response = self.llm_client.analyze(prompt)
            parsed = parse_llm_response(response.text, response.confidence)
            return AnalystResult(
                analyst_name='options',
                symbol=symbol,
                timeframe=timeframe,
                signal=parsed['signal'],
                confidence=parsed['confidence'],
                reasoning=parsed['reasoning'],
                data={'llm_model': response.model_used, 'data_source': 'llm'}
            )

        options_data = await self._fetch_options_data(symbol)
        iv = options_data.get('implied_volatility', 0.2)
        pc_ratio = options_data.get('put_call_ratio', 1.0)
        unusual = options_data.get('unusual_activity', False)

        signal, confidence = self._evaluate_options(iv, pc_ratio, unusual)

        return AnalystResult(
            analyst_name='options',
            symbol=symbol,
            timeframe=timeframe,
            signal=signal,
            confidence=confidence,
            reasoning=f'IV: {iv:.2f}, P/C: {pc_ratio:.2f}, Unusual: {unusual}',
            data=options_data
        )

    async def _fetch_options_data(self, symbol: str) -> dict:
        # TODO: Replace with real options data API
        return {
            'implied_volatility': 0.25,
            'put_call_ratio': 0.8,
            'unusual_activity': False,
            'greeks': {'delta': 0.5, 'gamma': 0.02, 'theta': -0.01}
        }

    def _evaluate_options(self, iv: float, pc_ratio: float, unusual: bool) -> tuple:
        if pc_ratio < 0.7 and not unusual:
            return ('BUY', 0.65)
        elif pc_ratio > 1.3:
            return ('SELL', 0.65)
        return ('HOLD', 0.5)

    def get_capabilities(self) -> list[str]:
        return list(self._capabilities)
