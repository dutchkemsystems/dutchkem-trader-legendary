"""
Feature 2: Sentiment-Enhanced Signal Filter
Pulls real-time sentiment from news APIs and social media to filter trades.
"""
import os
import json
import logging
from typing import Dict, Optional
from datetime import datetime, timezone, timedelta

log = logging.getLogger("sentiment")


class SentimentFilter:
    """Filter trades based on news and social media sentiment."""

    def __init__(self):
        self.sentiment_cache = {}
        self.cache_ttl = timedelta(minutes=30)
        self.min_confidence = 0.3

    def get_sentiment(self, symbol: str) -> Dict:
        """Get sentiment score for a symbol."""
        # Check cache
        if symbol in self.sentiment_cache:
            cached = self.sentiment_cache[symbol]
            if datetime.now(timezone.utc) - cached["timestamp"] < self.cache_ttl:
                return cached

        # Try to fetch real sentiment (fallback to neutral)
        sentiment = self._fetch_sentiment(symbol)

        # Cache result
        self.sentiment_cache[symbol] = {
            "score": sentiment["score"],
            "confidence": sentiment["confidence"],
            "source": sentiment["source"],
            "timestamp": datetime.now(timezone.utc),
        }

        return self.sentiment_cache[symbol]

    def _fetch_sentiment(self, symbol: str) -> Dict:
        """Fetch sentiment from available sources."""
        # Try NewsAPI if available
        newsapi_key = os.environ.get("NEWSAPI_KEY")
        if newsapi_key:
            try:
                return self._fetch_newsapi(symbol, newsapi_key)
            except Exception as e:
                log.warning(f"NewsAPI failed: {e}")

        # Try web search for sentiment
        try:
            return self._fetch_web_sentiment(symbol)
        except Exception as e:
            log.warning(f"Web sentiment failed: {e}")

        # Default: neutral sentiment
        return {"score": 0.0, "confidence": 0.0, "source": "neutral"}

    def _fetch_newsapi(self, symbol: str, api_key: str) -> Dict:
        """Fetch sentiment from NewsAPI."""
        import requests

        # Convert symbol to search terms
        base = symbol[:3] + "/" + symbol[3:] if len(symbol) == 6 else symbol
        query = f"{base} forex"

        url = f"https://newsapi.org/v2/everything"
        params = {
            "q": query,
            "apiKey": api_key,
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": 10,
        }

        response = requests.get(url, params=params, timeout=10)
        data = response.json()

        if data.get("status") == "ok" and data.get("articles"):
            # Simple sentiment based on headlines
            positive_words = ["surge", "rally", "gain", "rise", "bull", "up", "high", "strong"]
            negative_words = ["fall", "drop", "decline", "crash", "bear", "down", "low", "weak"]

            scores = []
            for article in data["articles"][:5]:
                title = article.get("title", "").lower()
                pos_count = sum(1 for w in positive_words if w in title)
                neg_count = sum(1 for w in negative_words if w in title)
                if pos_count + neg_count > 0:
                    scores.append((pos_count - neg_count) / (pos_count + neg_count))

            if scores:
                avg_score = sum(scores) / len(scores)
                return {
                    "score": avg_score,
                    "confidence": min(len(scores) / 5, 1.0),
                    "source": "newsapi",
                }

        return {"score": 0.0, "confidence": 0.0, "source": "newsapi_empty"}

    def _fetch_web_sentiment(self, symbol: str) -> Dict:
        """Fetch sentiment from web search — not configured."""
        return {"score": 0.0, "confidence": 0.0, "source": "not_configured"}

    def should_trade(self, symbol: str, direction: str) -> Dict:
        """Check if sentiment aligns with trade direction."""
        sentiment = self.get_sentiment(symbol)

        # Sentiment alignment
        if direction == "BUY":
            aligned = sentiment["score"] > -0.1  # Not strongly negative
        elif direction == "SELL":
            aligned = sentiment["score"] < 0.1  # Not strongly positive
        else:
            aligned = True

        # Confidence check
        if sentiment["confidence"] < self.min_confidence:
            # Low confidence sentiment — allow trade but note it
            return {
                "allow": True,
                "reason": "low_sentiment_confidence",
                "sentiment": sentiment,
            }

        return {
            "allow": aligned,
            "reason": "aligned" if aligned else "contrarian",
            "sentiment": sentiment,
        }
