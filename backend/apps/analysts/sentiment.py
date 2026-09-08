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

        social_data = await self._fetch_social_sentiment(symbol)
        fear_greed = await self._fetch_fear_greed()
        positioning = await self._fetch_positioning(symbol)

        composite_score = self._calculate_composite(social_data, fear_greed, positioning)

        if composite_score > 0.2:
            signal = 'BUY'
            confidence = min(0.5 + composite_score, 0.85)
        elif composite_score < -0.2:
            signal = 'SELL'
            confidence = min(0.5 + abs(composite_score), 0.85)
        else:
            signal = 'HOLD'
            confidence = 0.5

        return AnalystResult(
            analyst_name='sentiment',
            symbol=symbol,
            timeframe=timeframe,
            signal=signal,
            confidence=confidence,
            reasoning=f'Composite: {composite_score:.2f}, Fear/Greed: {fear_greed}',
            data={'social': social_data, 'fear_greed': fear_greed, 'positioning': positioning}
        )

    async def _fetch_social_sentiment(self, symbol: str) -> dict:
        # TODO: Replace with real social media API
        return {'twitter': 0.1, 'reddit': 0.2, 'telegram': 0.05}

    async def _fetch_fear_greed(self) -> int:
        # TODO: Replace with real Fear/Greed API
        return 55  # Neutral

    async def _fetch_positioning(self, symbol: str) -> dict:
        # TODO: Replace with real positioning data
        return {'long_ratio': 0.6, 'short_ratio': 0.4}

    def _calculate_composite(self, social: dict, fear_greed: int, positioning: dict) -> float:
        social_avg = sum(social.values()) / len(social) if social else 0
        fear_greed_normalized = (fear_greed - 50) / 50
        positioning_bias = positioning.get('long_ratio', 0.5) - 0.5
        return (social_avg + fear_greed_normalized + positioning_bias) / 3

    def get_capabilities(self) -> list[str]:
        return list(self._capabilities)
