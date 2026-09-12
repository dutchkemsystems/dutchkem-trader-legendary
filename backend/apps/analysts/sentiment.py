"""Sentiment Analyst — market fear/greed indicators + VIX + news headline NLP.

Data sources (all free, no API keys):
  - CBOE VIX via yfinance  (market fear gauge, VIX > 30 = fear)
  - Alternative.me Fear & Greed Index via requests  (crypto → risk-on/off proxy)
  - News headline polarity via simple keyword scoring  (reused from NewsAnalyst)
No API keys required.
"""
import logging
from typing import Optional

import requests
import yfinance as yf

from .base import BaseAnalyst, AnalystResult

log = logging.getLogger(__name__)

# ── Keyword-based sentiment (lightweight, no NLP library needed) ──────
_BULL_WORDS = {
    "rally", "surge", "jump", "gain", "rise", "bullish", "buy",
    "demand", "breakout", "recovery", "expansion", "hawkish", "stronger",
    "outperform", "beat", "upgrade", "risk-on", "rebound", "climb",
}
_BEAR_WORDS = {
    "crash", "plunge", "drop", "fall", "decline", "bearish", "sell",
    "panic", "recession", "contraction", "dovish", "weaker", "miss",
    "downgrade", "risk-off", "crisis", "default", "collapse", "tumble",
}


def _headline_sentiment(text: str) -> float:
    """Quick keyword sentiment in [-1, +1]."""
    words = set(text.lower().split())
    bull = len(words & _BULL_WORDS)
    bear = len(words & _BEAR_WORDS)
    total = bull + bear
    return (bull - bear) / total if total else 0.0


class SentimentAnalyst(BaseAnalyst):
    def __init__(self, llm_client=None):
        self.llm_client = llm_client
        self._capabilities = ["fear_greed_index", "vix_analysis", "social_sentiment"]

    async def analyze(self, symbol: str, timeframe: str) -> AnalystResult:
        if self.llm_client:
            from .prompts import build_prompt, parse_llm_response
            prompt = build_prompt("sentiment", symbol, timeframe)
            response = self.llm_client.analyze(prompt)
            parsed = parse_llm_response(response.text, response.confidence)
            return AnalystResult(
                analyst_name="sentiment",
                symbol=symbol,
                timeframe=timeframe,
                signal=parsed["signal"],
                confidence=parsed["confidence"],
                reasoning=parsed["reasoning"],
                data={"llm_model": response.model_used, "data_source": "llm"},
            )

        data = {}
        signals = []

        # 1) VIX — market fear gauge
        vix_value = self._fetch_vix()
        if vix_value is not None:
            data["vix"] = round(vix_value, 2)
            # VIX > 30 → extreme fear (risk-off → bullish USD as safe haven)
            # VIX < 15 → extreme greed (risk-on → bearish USD)
            if vix_value > 30:
                signals.append(("fear", 0.8, "VIX extremely high — market fear"))
            elif vix_value > 25:
                signals.append(("fear", 0.6, "VIX elevated — caution"))
            elif vix_value < 15:
                signals.append(("greed", 0.7, "VIX low — market complacent"))
            elif vix_value < 20:
                signals.append(("neutral", 0.5, "VIX normal range"))
            else:
                signals.append(("neutral", 0.5, f"VIX={vix_value:.1f} — moderate"))
        else:
            data["vix"] = None

        # 2) Crypto Fear & Greed Index — risk-on / risk-off proxy (with short timeout)
        fng = self._fetch_fear_greed()
        if fng is not None:
            data["fear_greed_index"] = fng
            # F&G > 75 = extreme greed → risk-on → bearish safe havens
            # F&G < 25 = extreme fear → risk-off → bullish safe havens
            if fng < 25:
                signals.append(("fear", 0.7, f"Crypto F&G={fng} — extreme fear"))
            elif fng < 40:
                signals.append(("fear", 0.5, f"Crypto F&G={fng} — fear"))
            elif fng > 75:
                signals.append(("greed", 0.7, f"Crypto F&G={fng} — extreme greed"))
            elif fng > 60:
                signals.append(("greed", 0.5, f"Crypto F&G={fng} — greed"))
            else:
                signals.append(("neutral", 0.5, f"Crypto F&G={fng} — neutral"))
        else:
            data["fear_greed_index"] = None

        # 3) USD sentiment from DXY movement
        dxy_signal = self._fetch_dxy_momentum()
        if dxy_signal is not None:
            data["dxy_momentum"] = dxy_signal
            if dxy_signal > 0.5:
                signals.append(("bullish_usd", 0.6, "DXY strengthening"))
            elif dxy_signal < -0.5:
                signals.append(("bearish_usd", 0.6, "DXY weakening"))
            else:
                signals.append(("neutral", 0.4, "DXY flat"))

        # Combine signals
        if not signals:
            return AnalystResult(
                analyst_name="sentiment",
                symbol=symbol,
                timeframe=timeframe,
                signal="HOLD",
                confidence=0.0,
                reasoning="No sentiment data available",
                data={"data_source": "none"},
                data_source="none",
            )

        # Count votes
        bull_votes = sum(1 for s in signals if s[0] in ("greed", "bullish_usd"))
        bear_votes = sum(1 for s in signals if s[0] in ("fear", "bearish_usd"))
        total = len(signals)
        avg_conf = sum(s[1] for s in signals) / total

        # For forex: fear in markets = USD bullish (safe haven)
        # Greed = USD bearish (risk-on, money flows out of USD)
        is_usd_pair = symbol.upper().startswith("USD") or symbol.upper().endswith("USD")

        if is_usd_pair:
            if bull_votes > bear_votes:
                signal = "BUY"
                confidence = min(avg_conf + 0.1, 0.85)
            elif bear_votes > bull_votes:
                signal = "SELL"
                confidence = min(avg_conf + 0.1, 0.85)
            else:
                signal = "HOLD"
                confidence = 0.45
        else:
            # Non-USD pairs: inverse interpretation
            if bull_votes > bear_votes:
                signal = "SELL"
                confidence = min(avg_conf, 0.75)
            elif bear_votes > bull_votes:
                signal = "BUY"
                confidence = min(avg_conf, 0.75)
            else:
                signal = "HOLD"
                confidence = 0.45

        reasoning = " | ".join(s[2] for s in signals)

        return AnalystResult(
            analyst_name="sentiment",
            symbol=symbol,
            timeframe=timeframe,
            signal=signal,
            confidence=confidence,
            reasoning=reasoning,
            data={
                "signals": [{"type": s[0], "conf": s[1], "reason": s[2]} for s in signals],
                "vix": data.get("vix"),
                "fear_greed": data.get("fear_greed_index"),
                "dxy_momentum": data.get("dxy_momentum"),
                "bull_votes": bull_votes,
                "bear_votes": bear_votes,
                "data_source": "yfinance+alternative_me",
            },
            data_source="yfinance+alternative_me",
        )

    def _fetch_vix(self) -> Optional[float]:
        """Fetch current VIX from CBOE via yfinance."""
        try:
            vix = yf.Ticker("^VIX")
            hist = vix.history(period="5d")
            if hist is not None and not hist.empty:
                return float(hist["Close"].iloc[-1])
        except Exception as e:
            log.warning(f"VIX fetch failed: {e}")
        return None

    def _fetch_fear_greed(self) -> Optional[int]:
        """Fetch Crypto Fear & Greed Index.

        Uses alternative.me with a very short timeout (3s).
        If it fails, returns None — the VIX is the primary fear gauge anyway.
        """
        try:
            resp = requests.get(
                "https://api.alternative.me/fng/?limit=1&format=json",
                timeout=3,
            )
            data = resp.json()
            return int(data["data"][0]["value"])
        except Exception:
            # Not critical — VIX is the primary fear gauge
            return None

    def _fetch_dxy_momentum(self) -> Optional[float]:
        """Fetch DXY 5-day price change as momentum signal."""
        try:
            dxy = yf.Ticker("DX-Y.NYB")
            hist = dxy.history(period="5d")
            if hist is not None and len(hist) >= 2:
                close_now = float(hist["Close"].iloc[-1])
                close_prev = float(hist["Close"].iloc[0])
                pct_change = ((close_now - close_prev) / close_prev) * 100
                return round(pct_change, 2)
        except Exception as e:
            log.warning(f"DXY momentum fetch failed: {e}")
        return None

    def get_capabilities(self) -> list[str]:
        return list(self._capabilities)
