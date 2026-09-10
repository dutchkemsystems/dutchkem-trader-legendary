"""
Feature 10: Alternative Data Integration
Uses on-chain metrics and other non-traditional data sources.
"""
import os
import logging
from typing import Dict, Optional
from datetime import datetime, timezone, timedelta

log = logging.getLogger("alternative_data")


class AlternativeData:
    """Integrate alternative data sources for signal enhancement."""

    def __init__(self):
        self.cache = {}
        self.cache_ttl = timedelta(hours=1)

    def get_onchain_data(self, symbol: str) -> Dict:
        """Get on-chain data for crypto symbols."""
        # Check if this is a crypto symbol
        if not any(crypto in symbol.upper() for crypto in ["BTC", "ETH", "SOL", "XRP"]):
            return {"available": False, "reason": "not_crypto"}

        # Try Glassnode API
        glassnode_key = os.environ.get("GLASSNODE_KEY")
        if glassnode_key:
            try:
                return self._fetch_glassnode(symbol, glassnode_key)
            except Exception as e:
                log.warning(f"Glassnode fetch failed: {e}")

        # Try CryptoQuant
        cryptoquant_key = os.environ.get("CRYPTOQUANT_KEY")
        if cryptoquant_key:
            try:
                return self._fetch_cryptoquant(symbol, cryptoquant_key)
            except Exception as e:
                log.warning(f"CryptoQuant fetch failed: {e}")

        return {"available": False, "reason": "no_api_key"}

    def _fetch_glassnode(self, symbol: str, api_key: str) -> Dict:
        """Fetch from Glassnode API."""
        import requests

        # Map symbol to asset
        asset = symbol[:3].lower()

        url = f"https://api.glassnode.com/v1/metrics/indicators/mvrv_z_score"
        params = {"a": asset, "api_key": api_key}

        response = requests.get(url, params=params, timeout=10)
        data = response.json()

        if data:
            latest = data[-1] if isinstance(data, list) else data
            return {
                "available": True,
                "mvrv_z_score": latest.get("v", 0),
                "signal": self._interpret_mvrv(latest.get("v", 0)),
                "source": "glassnode",
            }

        return {"available": False, "reason": "empty_response"}

    def _fetch_cryptoquant(self, symbol: str, api_key: str) -> Dict:
        """Fetch from CryptoQuant API."""
        import requests

        asset = symbol[:3].lower()

        url = f"https://api.cryptoquant.com/v1/btc/market-data/price-mvrv-ratio"
        params = {"api_key": api_key}

        response = requests.get(url, params=params, timeout=10)
        data = response.json()

        if data.get("result"):
            latest = data["result"][-1]
            return {
                "available": True,
                "mvrv_ratio": latest.get("mvrv_ratio", 0),
                "signal": self._interpret_mvrv(latest.get("mvrv_ratio", 0)),
                "source": "cryptoquant",
            }

        return {"available": False, "reason": "empty_response"}

    def _interpret_mvrv(self, mvrv: float) -> str:
        """Interpret MVRV Z-Score."""
        if mvrv > 7:
            return "extremely_overvalued"
        elif mvrv > 3:
            return "overvalued"
        elif mvrv > 0:
            return "fair_value"
        elif mvrv > -3:
            return "undervalued"
        else:
            return "extremely_undervalued"

    def get_sentiment_data(self, symbol: str) -> Dict:
        """Get social media sentiment data."""
        # Check cache
        cache_key = f"sentiment_{symbol}"
        if cache_key in self.cache:
            cached = self.cache[cache_key]
            if datetime.now(timezone.utc) - cached["timestamp"] < self.cache_ttl:
                return cached

        # Try StockTwits API (free)
        try:
            data = self._fetch_stocktwits(symbol)
            if data:
                self.cache[cache_key] = {**data, "timestamp": datetime.now(timezone.utc)}
                return data
        except Exception as e:
            log.warning(f"StockTwits fetch failed: {e}")

        return {"available": False, "reason": "no_data"}

    def _fetch_stocktwits(self, symbol: str) -> Dict:
        """Fetch from StockTwits API."""
        import requests

        url = f"https://api.stocktwits.com/api/2/streams/symbol/{symbol}.json"
        response = requests.get(url, timeout=10)
        data = response.json()

        if data.get("messages"):
            messages = data["messages"][:20]
            bullish = sum(1 for m in messages if m.get("entities", {}).get("sentiment", {}).get("basic") == "Bullish")
            bearish = sum(1 for m in messages if m.get("entities", {}).get("sentiment", {}).get("basic") == "Bearish")

            total = bullish + bearish
            if total > 0:
                sentiment_score = (bullish - bearish) / total
                return {
                    "available": True,
                    "score": sentiment_score,
                    "bullish": bullish,
                    "bearish": bearish,
                    "source": "stocktwits",
                }

        return {"available": False, "reason": "no_messages"}

    def get_signal(self, symbol: str) -> Dict:
        """Get combined alternative data signal."""
        signals = []

        # On-chain data
        onchain = self.get_onchain_data(symbol)
        if onchain.get("available"):
            signal = onchain.get("signal", "neutral")
            if "overvalued" in signal:
                signals.append({"direction": "SELL", "confidence": 0.6, "source": "onchain"})
            elif "undervalued" in signal:
                signals.append({"direction": "BUY", "confidence": 0.6, "source": "onchain"})

        # Social sentiment
        sentiment = self.get_sentiment_data(symbol)
        if sentiment.get("available"):
            score = sentiment.get("score", 0)
            if abs(score) > 0.3:
                direction = "BUY" if score > 0 else "SELL"
                signals.append({"direction": direction, "confidence": abs(score), "source": "social"})

        # Combine signals
        if not signals:
            return {"available": False, "reason": "no_signals"}

        buy_signals = [s for s in signals if s["direction"] == "BUY"]
        sell_signals = [s for s in signals if s["direction"] == "SELL"]

        if buy_signals and not sell_signals:
            avg_conf = sum(s["confidence"] for s in buy_signals) / len(buy_signals)
            return {"available": True, "direction": "BUY", "confidence": avg_conf, "sources": [s["source"] for s in buy_signals]}
        elif sell_signals and not buy_signals:
            avg_conf = sum(s["confidence"] for s in sell_signals) / len(sell_signals)
            return {"available": True, "direction": "SELL", "confidence": avg_conf, "sources": [s["source"] for s in sell_signals]}
        else:
            return {"available": True, "direction": "NEUTRAL", "confidence": 0, "sources": ["conflicting"]}
