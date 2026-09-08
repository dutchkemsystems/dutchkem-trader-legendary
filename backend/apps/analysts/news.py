from .base import BaseAnalyst, AnalystResult


class NewsAnalyst(BaseAnalyst):
    def __init__(self, llm_client=None):
        self.llm_client = llm_client
        self._capabilities = ['sentiment_analysis', 'keyword_extraction', 'event_detection']

    async def analyze(self, symbol: str, timeframe: str) -> AnalystResult:
        if self.llm_client:
            from .prompts import build_prompt, parse_llm_response
            prompt = build_prompt('news', symbol, timeframe)
            response = self.llm_client.analyze(prompt)
            parsed = parse_llm_response(response.text, response.confidence)
            return AnalystResult(
                analyst_name='news',
                symbol=symbol,
                timeframe=timeframe,
                signal=parsed['signal'],
                confidence=parsed['confidence'],
                reasoning=parsed['reasoning'],
                data={'llm_model': response.model_used, 'data_source': 'llm'}
            )

        news_data = await self._fetch_news(symbol)
        sentiment_score = self._analyze_sentiment(news_data)
        keywords = self._extract_keywords(news_data)

        if sentiment_score > 0.3:
            signal = 'BUY'
            confidence = min(0.5 + sentiment_score, 0.9)
        elif sentiment_score < -0.3:
            signal = 'SELL'
            confidence = min(0.5 + abs(sentiment_score), 0.9)
        else:
            signal = 'HOLD'
            confidence = 0.5

        return AnalystResult(
            analyst_name='news',
            symbol=symbol,
            timeframe=timeframe,
            signal=signal,
            confidence=confidence,
            reasoning=f'Sentiment: {sentiment_score:.2f}, Keywords: {", ".join(keywords[:3])}',
            data={'sentiment_score': sentiment_score, 'keywords': keywords, 'article_count': len(news_data)}
        )

    async def _fetch_news(self, symbol: str) -> list:
        # TODO: Replace with real News API
        return [{'title': f'News about {symbol}', 'content': 'Sample content', 'sentiment': 0.1}]

    def _analyze_sentiment(self, news: list) -> float:
        if not news:
            return 0.0
        sentiments = [item.get('sentiment', 0.0) for item in news]
        return sum(sentiments) / len(sentiments)

    def _extract_keywords(self, news: list) -> list:
        keywords = set()
        for item in news:
            words = item.get('content', '').split()
            keywords.update(words[:5])
        return list(keywords)[:10]

    def get_capabilities(self) -> list[str]:
        return list(self._capabilities)
