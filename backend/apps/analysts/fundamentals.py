from .base import BaseAnalyst, AnalystResult


class FundamentalsAnalyst(BaseAnalyst):
    def __init__(self, llm_client=None):
        self.llm_client = llm_client
        self._capabilities = ['financial_ratios', 'earnings_analysis', 'valuation']

    async def analyze(self, symbol: str, timeframe: str) -> AnalystResult:
        if self.llm_client:
            from .prompts import build_prompt, parse_llm_response
            prompt = build_prompt('fundamentals', symbol, timeframe)
            response = self.llm_client.analyze(prompt)
            parsed = parse_llm_response(response.text, response.confidence)
            return AnalystResult(
                analyst_name='fundamentals',
                symbol=symbol,
                timeframe=timeframe,
                signal=parsed['signal'],
                confidence=parsed['confidence'],
                reasoning=parsed['reasoning'],
                data={'llm_model': response.model_used, 'data_source': 'llm'}
            )

        # No fundamentals API configured — return clear "no data"
        return AnalystResult(
            analyst_name='fundamentals',
            symbol=symbol,
            timeframe=timeframe,
            signal='HOLD',
            confidence=0.0,
            reasoning='No fundamentals API configured — requires Yahoo Finance/Finnhub API',
            data={'error': 'no_fundamentals_api', 'data_source': 'none'}
        )

    def get_capabilities(self) -> list[str]:
        return list(self._capabilities)
