from .base import BaseAnalyst, AnalystResult


class OptionsAnalyst(BaseAnalyst):
    def __init__(self, llm_client=None):
        self.llm_client = llm_client
        self._capabilities = ['implied_volatility', 'put_call_ratio', 'greeks_analysis']

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

        # Options data limited for forex — return clear "no data"
        return AnalystResult(
            analyst_name='options',
            symbol=symbol,
            timeframe=timeframe,
            signal='HOLD',
            confidence=0.0,
            reasoning='No options API configured — requires CBOE/IBKR API',
            data={'error': 'no_options_api', 'data_source': 'none'}
        )

    def get_capabilities(self) -> list[str]:
        return list(self._capabilities)
