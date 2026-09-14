"""News Analyst — live forex news from RSS feeds with keyword sentiment.

Uses feedparser (already installed) to pull headlines from:
  - ForexLive, DailyFX, FXStreet, Investing.com, Reuters Finance
Then applies a keyword-scoring model to derive BUY/SELL/HOLD + confidence.
No API keys required. ~100 headlines scanned per cycle.
"""
import logging
import re
from typing import Optional

import feedparser

from .base import BaseAnalyst, AnalystResult

log = logging.getLogger(__name__)

# ── RSS feeds for forex / macro news (verified working) ──────────────
_FEEDS = {
    "yahoo_usd": "https://feeds.finance.yahoo.com/rss/2.0/headline?s=DX-Y.NYB&region=US&lang=en-US",
    "yahoo_eurusd": "https://feeds.finance.yahoo.com/rss/2.0/headline?s=EURUSD=X&region=US&lang=en-US",
    "investing": "https://www.investing.com/rss/news.rss",
    "cnbc_economy": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258",
    "cnbc_world": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100727362",
    "bbc_business": "https://feeds.bbci.co.uk/news/business/rss.xml",
}

# ── Keyword dictionaries for bullish / bearish scoring ────────────────
_BULLISH = {
    "rally", "rallies", "surge", "surges", "soar", "soars", "jump", "jumps",
    "gain", "gains", "rise", "rises", "higher", "up", "strong", "strength",
    "bullish", "buy", "demand", "support", "breakout", "upgrade", "beat",
    "exceeds", "outperform", "recovery", "expansion", "hawkish", "tightening",
    "rate hike", "rate increase", "stronger", "appreciate", "appreciation",
    "rebound", "recover", "climb", "gains momentum", "risk-on",
}
_BEARISH = {
    "crash", "plunge", "plunges", "drop", "drops", "fall", "falls",
    "decline", "declines", "slump", "slumps", "tumble", "tumbles",
    "lower", "down", "weak", "weakness", "bearish", "sell", "oversupply",
    "resistance", "downgrade", "miss", "underperform", "recession",
    "contraction", "dovish", "easing", "rate cut", "rate decrease",
    "weaker", "depreciate", "depreciation", "crisis", "panic", "risk-off",
    "default", "layoffs", "unemployment", "inflation surge",
}

# Currency → associated keywords to boost relevance
_CURRENCY_KEYWORDS = {
    "USD": {"fed", "federal reserve", "usd", "dollar", "treasury", "yield", "cpi", "nfp", "nonfarm", "powell", "fomc"},
    "EUR": {"ecb", "euro", "eur", "lagarde", "eurozone", "eu zone"},
    "GBP": {"boe", "gbp", "pound", "sterling", "uk", "british"},
    "JPY": {"boj", "jpy", "yen", "japan", "tokyo"},
    "CHF": {"snb", "chf", "franc", "swiss"},
    "AUD": {"rba", "aud", "aussie", "australia", "commodity currency"},
    "CAD": {"boc", "cad", "loonie", "canada", "oil"},
    "NZD": {"rbnz", "nzd", "kiwi", "new zealand"},
}


def _score_headline(title: str, summary: str = "") -> float:
    """Return sentiment score in [-1, +1] from keyword matching."""
    text = (title + " " + summary).lower()
    bull = sum(1 for w in _BULLISH if w in text)
    bear = sum(1 for w in _BEARISH if w in text)
    total = bull + bear
    if total == 0:
        return 0.0
    return (bull - bear) / total


def _extract_currency_relevance(title: str, summary: str = "") -> dict:
    """Count which currencies are mentioned and relevance."""
    text = (title + " " + summary).lower()
    scores = {}
    for ccy, keywords in _CURRENCY_KEYWORDS.items():
        hits = sum(1 for kw in keywords if kw in text)
        if hits > 0:
            scores[ccy] = hits
    return scores


def _symbol_to_currencies(symbol: str) -> list[str]:
    """Extract base/quote currencies from a forex pair symbol."""
    symbol = symbol.upper().replace("/", "")
    if len(symbol) == 6:
        return [symbol[:3], symbol[3:]]
    return []


class NewsAnalyst(BaseAnalyst):
    def __init__(self, llm_client=None):
        self.llm_client = llm_client
        self._capabilities = ["sentiment_analysis", "keyword_extraction", "event_detection"]
        self._max_articles = 30  # per feed

    async def analyze(self, symbol: str, timeframe: str) -> AnalystResult:
        if self.llm_client:
            from .prompts import build_prompt, parse_llm_response
            prompt = build_prompt("news", symbol, timeframe)
            response = self.llm_client.analyze(prompt)
            parsed = parse_llm_response(response.text, response.confidence)
            return AnalystResult(
                analyst_name="news",
                symbol=symbol,
                timeframe=timeframe,
                signal=parsed["signal"],
                confidence=parsed["confidence"],
                reasoning=parsed["reasoning"],
                data={"llm_model": response.model_used, "data_source": "llm"},
            )

        articles = self._fetch_news()
        if not articles:
            return AnalystResult(
                analyst_name="news",
                symbol=symbol,
                timeframe=timeframe,
                signal="HOLD",
                confidence=0.0,
                reasoning="No articles fetched from RSS feeds",
                data={"error": "no_articles", "article_count": 0, "data_source": "rss"},
                data_source="rss",
            )

        # Filter articles relevant to this symbol's currencies
        target_ccys = _symbol_to_currencies(symbol)
        relevant = []
        general = []
        for art in articles:
            ccy_hits = _extract_currency_relevance(art.get("title", ""), art.get("summary", ""))
            if any(ccy in ccy_hits for ccy in target_ccys):
                art["_relevance"] = ccy_hits
                relevant.append(art)
            elif not target_ccys:
                general.append(art)

        # Use relevant articles, fall back to general if none match
        pool = relevant if relevant else general if general else articles[:20]

        if not pool:
            return AnalystResult(
                analyst_name="news",
                symbol=symbol,
                timeframe=timeframe,
                signal="HOLD",
                confidence=0.0,
                reasoning=f"No relevant news found for {symbol}",
                data={"article_count": 0, "data_source": "rss"},
                data_source="rss",
            )

        # Score each headline
        scores = [_score_headline(a.get("title", ""), a.get("summary", "")) for a in pool]
        avg_score = sum(scores) / len(scores) if scores else 0.0

        # Determine signal (lowered thresholds for more directional signals)
        if avg_score > 0.05:
            signal = "BUY"
            confidence = min(0.4 + abs(avg_score) * 0.4, 0.85)
        elif avg_score < -0.05:
            signal = "SELL"
            confidence = min(0.4 + abs(avg_score) * 0.4, 0.85)
        else:
            signal = "HOLD"
            confidence = 0.45

        # Top headlines for reasoning
        top_bull = [(s, a.get("title", "")) for s, a in zip(scores, pool) if s > 0][:2]
        top_bear = [(s, a.get("title", "")) for s, a in zip(scores, pool) if s < 0][:2]
        reasoning_parts = [f"Scored {len(pool)} articles (avg={avg_score:.2f})"]
        if top_bull:
            reasoning_parts.append("Bull: " + "; ".join(t[:60] for _, t in top_bull))
        if top_bear:
            reasoning_parts.append("Bear: " + "; ".join(t[:60] for _, t in top_bear))

        keywords = self._extract_keywords(pool)

        return AnalystResult(
            analyst_name="news",
            symbol=symbol,
            timeframe=timeframe,
            signal=signal,
            confidence=confidence,
            reasoning=" | ".join(reasoning_parts),
            data={
                "sentiment_score": round(avg_score, 3),
                "article_count": len(pool),
                "relevant_count": len(relevant),
                "keywords": keywords[:8],
                "top_bull": [t for _, t in top_bull],
                "top_bear": [t for _, t in top_bear],
                "data_source": "rss",
            },
            data_source="rss",
        )

    def _fetch_news(self) -> list[dict]:
        """Fetch headlines from RSS feeds. Returns list of {title, summary, source, link}."""
        articles = []
        for feed_name, url in _FEEDS.items():
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[: self._max_articles]:
                    articles.append(
                        {
                            "title": entry.get("title", ""),
                            "summary": entry.get("summary", "")[:300],
                            "source": feed_name,
                            "link": entry.get("link", ""),
                            "published": entry.get("published", ""),
                        }
                    )
            except Exception as e:
                log.debug(f"RSS feed {feed_name} failed: {e}")
        log.info(f"NEWS: Fetched {len(articles)} articles from {_FEEDS.__len__()} RSS feeds")
        return articles

    def _extract_keywords(self, articles: list[dict]) -> list[str]:
        """Extract most frequent meaningful words from headlines."""
        stop = {
            "the", "a", "an", "in", "on", "at", "to", "for", "of", "with",
            "and", "or", "but", "is", "are", "was", "were", "be", "been",
            "has", "have", "had", "do", "does", "did", "will", "would",
            "could", "should", "may", "might", "shall", "can", "its", "it",
            "that", "this", "these", "those", "from", "by", "as", "into",
            "vs", "vs.", "after", "before", "more", "than", "not", "no",
            "up", "down", "over", "about", "after", "says", "said",
        }
        freq: dict[str, int] = {}
        for art in articles:
            words = re.findall(r"[a-z]+", (art.get("title", "") + " " + art.get("summary", "")).lower())
            for w in words:
                if len(w) > 2 and w not in stop:
                    freq[w] = freq.get(w, 0) + 1
        return [w for w, _ in sorted(freq.items(), key=lambda x: -x[1])[:10]]

    def get_capabilities(self) -> list[str]:
        return list(self._capabilities)
