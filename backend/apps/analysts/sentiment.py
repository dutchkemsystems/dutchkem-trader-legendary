from .base import BaseAnalyst, AnalystResult


class SentimentAnalyst(BaseAnalyst):
    def __init__(self, llm_client=None):
        self.llm_client = llm_client
        self._capabilities = ['social_sentiment', 'fear_greed_index', 'positioning_data']

    async def analyze(self, symbol: str, timeframe: str) -> AnalystResult:
        if self.llm_client:
            from .prompts import build_prompt, parse_llm_response
            prompt = build_prompt('sentiment', symbol, timeframe)
            response = self.llm_client.analyze(prompt)
            parsed = parse_llm_response(response.text, response.confidence)
            return AnalystResult(
                analyst_name='sentiment',
                symbol=symbol,
                timeframe=timeframe,
                signal=parsed['signal'],
                confidence=parsed['confidence'],
                reasoning=parsed['reasoning'],
                data={'llm_model': response.model_used, 'data_source': 'llm'}
            )

        # No sentiment API configured — return clear "no data"
        return AnalystResult(
            analyst_name='sentiment',
            symbol=symbol,
            timeframe=timeframe,
            signal='HOLD',
            confidence=0.0,
            reasoning='No sentiment API configured — requires Twitter/Reddit/Alternative.me APIs',
            data={'error': 'no_sentiment_api', 'data_source': 'none'}
        )

    def get_capabilities(self) -> list[str]:
        return list(self._capabilities)
