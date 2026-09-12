from .base import BaseAnalyst, AnalystResult


class MacroAnalyst(BaseAnalyst):
    def __init__(self, llm_client=None):
        self.llm_client = llm_client
        self._capabilities = ['economic_indicators', 'interest_rates', 'gdp_analysis']

    async def analyze(self, symbol: str, timeframe: str) -> AnalystResult:
        if self.llm_client:
            from .prompts import build_prompt, parse_llm_response
            prompt = build_prompt('macro', symbol, timeframe)
            response = self.llm_client.analyze(prompt)
            parsed = parse_llm_response(response.text, response.confidence)
            return AnalystResult(
                analyst_name='macro',
                symbol=symbol,
                timeframe=timeframe,
                signal=parsed['signal'],
                confidence=parsed['confidence'],
                reasoning=parsed['reasoning'],
                data={'llm_model': response.model_used, 'data_source': 'llm'}
            )

        # No macro API configured — return clear "no data"
        return AnalystResult(
            analyst_name='macro',
            symbol=symbol,
            timeframe=timeframe,
            signal='HOLD',
            confidence=0.0,
            reasoning='No macro API configured — requires FRED/Trading Economics API',
            data={'error': 'no_macro_api', 'data_source': 'none'},
            data_source='none'
        )

    def get_capabilities(self) -> list[str]:
        return list(self._capabilities)
