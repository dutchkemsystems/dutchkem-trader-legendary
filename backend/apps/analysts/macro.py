"""Macro Analyst — real macroeconomic indicators via yfinance.

Fetches live data for:
  - DXY (US Dollar Index)
  - US 10Y / 2Y Treasury yields  (yield curve)
  - Gold, Oil, Copper, Silver  (commodity correlations)
  - S&P 500, Nikkei 225  (equity risk)
  - VIX  (volatility)
All via yfinance — free, no API key required.
"""
import logging
from typing import Optional

import yfinance as yf

from .base import BaseAnalyst, AnalystResult

log = logging.getLogger(__name__)

# Symbol mapping: which macro indicators matter for each currency pair
_MACRO_MAP = {
    "USD": {
        "tickers": {
            "DXY": "DX-Y.NYB",
            "US10Y": "^TNX",
            "US2Y": "^IRX",     # 13-week T-bill as proxy
            "SP500": "^GSPC",
            "VIX": "^VIX",
        },
        "interpretation": "higher yields + strong DXY = USD bullish",
    },
    "EUR": {
        "tickers": {
            "DXY": "DX-Y.NYB",
            "EUROSTOXX": "^STOXX50E",
            "BUND": "^TNX",     # Use US as proxy, EUR inversely correlated
        },
        "interpretation": "weaker DXY = EUR bullish",
    },
    "GBP": {
        "tickers": {
            "DXY": "DX-Y.NYB",
            "FTSE": "^FTSE",
            "UK10Y": "^TNX",
        },
        "interpretation": "FTSE rally + strong GBP = GBP bullish",
    },
    "JPY": {
        "tickers": {
            "DXY": "DX-Y.NYB",
            "NIKKEI": "^N225",
            "US10Y": "^TNX",
            "GOLD": "GC=F",
        },
        "interpretation": "low yields + risk-off = JPY bullish (safe haven)",
    },
    "CHF": {
        "tickers": {
            "DXY": "DX-Y.NYB",
            "GOLD": "GC=F",
            "US10Y": "^TNX",
        },
        "interpretation": "risk-off + low yields = CHF bullish (safe haven)",
    },
    "AUD": {
        "tickers": {
            "DXY": "DX-Y.NYB",
            "GOLD": "GC=F",
            "COPPER": "HG=F",
            "IRON": "^SGXFEF",
        },
        "interpretation": "commodity rally + risk-on = AUD bullish",
    },
    "CAD": {
        "tickers": {
            "DXY": "DX-Y.NYB",
            "OIL": "CL=F",
            "US10Y": "^TNX",
        },
        "interpretation": "oil rally = CAD bullish (petro-currency)",
    },
    "NZD": {
        "tickers": {
            "DXY": "DX-Y.NYB",
            "GOLD": "GC=F",
            "AUDUSD": "AUDUSD=X",
        },
        "interpretation": "commodity rally + risk-on = NZD bullish",
    },
}


class MacroAnalyst(BaseAnalyst):
    def __init__(self, llm_client=None):
        self.llm_client = llm_client
        self._capabilities = ["economic_indicators", "interest_rates", "commodity_analysis"]

    async def analyze(self, symbol: str, timeframe: str) -> AnalystResult:
        if self.llm_client:
            from .prompts import build_prompt, parse_llm_response
            prompt = build_prompt("macro", symbol, timeframe)
            response = self.llm_client.analyze(prompt)
            parsed = parse_llm_response(response.text, response.confidence)
            return AnalystResult(
                analyst_name="macro",
                symbol=symbol,
                timeframe=timeframe,
                signal=parsed["signal"],
                confidence=parsed["confidence"],
                reasoning=parsed["reasoning"],
                data={"llm_model": response.model_used, "data_source": "llm"},
            )

        # Determine relevant currencies
        sym = symbol.upper().replace("/", "")
        base_ccy = sym[:3] if len(sym) >= 3 else "USD"
        quote_ccy = sym[3:] if len(sym) >= 6 else "USD"

        # Collect macro data for both currencies
        base_config = _MACRO_MAP.get(base_ccy, _MACRO_MAP["USD"])
        quote_config = _MACRO_MAP.get(quote_ccy, _MACRO_MAP["USD"])

        all_tickers = {}
        all_tickers.update({f"BASE_{k}": v for k, v in base_config["tickers"].items()})
        all_tickers.update({f"QUOTE_{k}": v for k, v in quote_config["tickers"].items()})

        macro_data = self._fetch_macro(all_tickers)
        if not macro_data:
            return AnalystResult(
                analyst_name="macro",
                symbol=symbol,
                timeframe=timeframe,
                signal="HOLD",
                confidence=0.0,
                reasoning="Could not fetch any macro data",
                data={"error": "fetch_failed", "data_source": "yfinance"},
                data_source="yfinance",
            )

        # Analyze macro conditions
        bull_score = 0
        bear_score = 0
        reasoning_parts = []

        # DXY analysis (most important for forex)
        dxy = macro_data.get("BASE_DXY") or macro_data.get("QUOTE_DXY")
        if dxy is not None:
            if dxy > 105:
                bull_score += 1  # Strong USD
                reasoning_parts.append(f"DXY={dxy:.1f} (strong USD)")
            elif dxy < 100:
                bear_score += 1  # Weak USD
                reasoning_parts.append(f"DXY={dxy:.1f} (weak USD)")
            else:
                reasoning_parts.append(f"DXY={dxy:.1f} (neutral)")

        # Yield curve (US10Y - US2Y)
        us10y = macro_data.get("BASE_US10Y")
        us2y = macro_data.get("BASE_US2Y")
        if us10y is not None and us2y is not None:
            spread = us10y - us2y
            if spread > 0.5:
                bull_score += 1
                reasoning_parts.append(f"Yield spread={spread:.2f}% (healthy)")
            elif spread < 0:
                bear_score += 1
                reasoning_parts.append(f"Yield spread={spread:.2f}% (inverted!)")
            else:
                reasoning_parts.append(f"Yield spread={spread:.2f}% (flat)")

        # Commodity signals
        gold = macro_data.get("BASE_GOLD") or macro_data.get("QUOTE_GOLD")
        oil = macro_data.get("BASE_OIL") or macro_data.get("QUOTE_OIL")
        copper = macro_data.get("BASE_COPPER") or macro_data.get("QUOTE_COPPER")

        if gold is not None:
            reasoning_parts.append(f"Gold=${gold:.0f}")
        if oil is not None:
            if oil > 80:
                bull_score += 1  # High oil → inflation → hawkish → USD+
                reasoning_parts.append(f"Oil=${oil:.1f} (elevated)")
            elif oil < 60:
                bear_score += 1
                reasoning_parts.append(f"Oil=${oil:.1f} (low)")
            else:
                reasoning_parts.append(f"Oil=${oil:.1f}")

        if copper is not None:
            reasoning_parts.append(f"Copper=${copper:.2f}")

        # Equity risk
        sp500 = macro_data.get("BASE_SP500")
        nikkei = macro_data.get("BASE_NIKKEI")
        if sp500 is not None:
            reasoning_parts.append(f"SPX={sp500:.0f}")
        if nikkei is not None:
            reasoning_parts.append(f"Nikkei={nikkei:.0f}")

        # VIX
        vix = macro_data.get("BASE_VIX")
        if vix is not None:
            if vix > 30:
                bear_score += 1  # High fear → risk-off
                reasoning_parts.append(f"VIX={vix:.1f} (high fear)")
            elif vix < 15:
                bull_score += 1  # Low fear → risk-on
                reasoning_parts.append(f"VIX={vix:.1f} (complacent)")

        # Determine signal based on base currency bias
        total = bull_score + bear_score
        if total == 0:
            signal = "HOLD"
            confidence = 0.4
        elif bull_score > bear_score:
            signal = "BUY"
            confidence = min(0.5 + (bull_score - bear_score) / max(total, 1) * 0.3, 0.85)
        else:
            signal = "SELL"
            confidence = min(0.5 + (bear_score - bull_score) / max(total, 1) * 0.3, 0.85)

        return AnalystResult(
            analyst_name="macro",
            symbol=symbol,
            timeframe=timeframe,
            signal=signal,
            confidence=confidence,
            reasoning=f"Macro ({base_ccy}/{quote_ccy}): " + " | ".join(reasoning_parts),
            data={
                "macro_data": {k: round(v, 2) if v else None for k, v in macro_data.items()},
                "bull_score": bull_score,
                "bear_score": bear_score,
                "base_ccy": base_ccy,
                "quote_ccy": quote_ccy,
                "data_source": "yfinance",
            },
            data_source="yfinance",
        )

    def _fetch_macro(self, tickers: dict[str, str]) -> dict[str, float]:
        """Fetch latest close for a dict of {label: ticker}."""
        result = {}
        for label, ticker in tickers.items():
            try:
                t = yf.Ticker(ticker)
                hist = t.history(period="5d")
                if hist is not None and not hist.empty:
                    result[label] = float(hist["Close"].iloc[-1])
            except Exception as e:
                log.debug(f"Macro fetch {label} ({ticker}) failed: {e}")
        return result

    def get_capabilities(self) -> list[str]:
        return list(self._capabilities)
