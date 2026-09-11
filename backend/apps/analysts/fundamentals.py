"""
Fundamentals Analyst — Uses yfinance for currency-related fundamentals.
Fetches central bank rates, bond yields, and economic indicators.
No API key required.
"""
import logging
from datetime import datetime, timezone
from .base import BaseAnalyst, AnalystResult

log = logging.getLogger("fundamentals_analyst")

# Map forex pairs to valid yfinance tickers
PAIR_FUNDAMENTALS = {
    "EURUSD": {"dxy": "DX-Y.NYB", "us10y": "^TNX", "gold": "GC=F"},
    "GBPUSD": {"dxy": "DX-Y.NYB", "us10y": "^TNX"},
    "USDCHF": {"dxy": "DX-Y.NYB", "us10y": "^TNX", "gold": "GC=F"},
    "AUDUSD": {"dxy": "DX-Y.NYB", "us10y": "^TNX", "copper": "HG=F"},
    "NZDUSD": {"dxy": "DX-Y.NYB", "us10y": "^TNX"},
    "USDCAD": {"dxy": "DX-Y.NYB", "us10y": "^TNX", "oil": "CL=F"},
    "EURGBP": {"dxy": "DX-Y.NYB", "gold": "GC=F"},
    "EURJPY": {"dxy": "DX-Y.NYB", "us10y": "^TNX", "nikkei": "^N225"},
    "GBPJPY": {"dxy": "DX-Y.NYB", "us10y": "^TNX", "nikkei": "^N225"},
    "USDJPY": {"dxy": "DX-Y.NYB", "us10y": "^TNX", "nikkei": "^N225"},
}


class FundamentalsAnalyst(BaseAnalyst):
    def __init__(self, llm_client=None):
        self.llm_client = llm_client
        self._capabilities = [
            "central_bank_rates",
            "bond_yields",
            "dollar_index",
            "commodity_correlation",
            "yield_spread",
        ]

    async def analyze(self, symbol: str, timeframe: str) -> AnalystResult:
        # Try LLM first
        if self.llm_client:
            try:
                from .prompts import build_prompt, parse_llm_response
                prompt = (
                    f"Analyze the fundamental economic conditions for {symbol}. "
                    f"Consider: interest rate differentials, GDP growth, trade balance, "
                    f"inflation differentials, central bank policy outlook. "
                    f"Provide signal (BUY/SELL/HOLD) with confidence and reasoning."
                )
                response = self.llm_client.analyze(prompt)
                parsed = parse_llm_response(response.text, response.confidence)
                return AnalystResult(
                    analyst_name="fundamentals",
                    symbol=symbol,
                    timeframe=timeframe,
                    signal=parsed["signal"],
                    confidence=parsed["confidence"],
                    reasoning=parsed["reasoning"],
                    data={"llm_model": response.model_used, "data_source": "llm"},
                )
            except Exception as e:
                log.debug(f"LLM fundamentals failed: {e}")

        # Fallback: yfinance data
        try:
            import yfinance as yf
        except ImportError:
            return AnalystResult(
                analyst_name="fundamentals",
                symbol=symbol,
                timeframe=timeframe,
                signal="HOLD",
                confidence=0.0,
                reasoning="yfinance not installed",
                data={"error": "yfinance_missing"},
            )

        tickers_needed = PAIR_FUNDAMENTALS.get(symbol, {})
        if not tickers_needed:
            return AnalystResult(
                analyst_name="fundamentals",
                symbol=symbol,
                timeframe=timeframe,
                signal="HOLD",
                confidence=0.0,
                reasoning=f"No fundamental data mapping for {symbol}",
                data={"error": "no_mapping"},
            )

        data = {}
        for key, ticker in tickers_needed.items():
            try:
                t = yf.Ticker(ticker)
                hist = t.history(period="5d")
                if len(hist) > 0:
                    current = float(hist["Close"].iloc[-1])
                    prev = float(hist["Close"].iloc[-2]) if len(hist) > 1 else current
                    change_pct = (current - prev) / prev * 100 if prev != 0 else 0
                    data[key] = {"value": round(current, 4), "change_pct": round(change_pct, 2), "ticker": ticker}
            except Exception as e:
                log.debug(f"Failed to fetch {ticker} for {key}: {e}")

        if not data:
            return AnalystResult(
                analyst_name="fundamentals",
                symbol=symbol,
                timeframe=timeframe,
                signal="HOLD",
                confidence=0.0,
                reasoning="Could not fetch fundamental data from yfinance",
                data={"error": "fetch_failed"},
            )

        signal = "HOLD"
        confidence = 0.0
        reasoning_parts = []

        if "us10y" in data and "dxy" in data:
            us10y = data["us10y"]["value"]
            dxy_change = data["dxy"].get("change_pct", 0)
            reasoning_parts.append(f"US 10Y={us10y:.2f}%, DXY={dxy_change:+.2f}%")
            if us10y > 4.5:
                reasoning_parts.append("High US yields = USD bullish")
                confidence = min(confidence + 0.15, 0.7)
            elif us10y < 3.5:
                reasoning_parts.append("Low US yields = USD bearish")
                confidence = min(confidence + 0.15, 0.7)

        if "oil" in data:
            oil_change = data["oil"].get("change_pct", 0)
            reasoning_parts.append(f"Oil={oil_change:+.2f}%")
            if symbol == "USDCAD":
                signal = "SELL" if oil_change > 1 else "BUY" if oil_change < -1 else "HOLD"
                confidence = min(confidence + 0.1, 0.6)

        if "copper" in data:
            copper_change = data["copper"].get("change_pct", 0)
            reasoning_parts.append(f"Copper={copper_change:+.2f}%")
            if symbol == "AUDUSD":
                signal = "BUY" if copper_change > 1 else "SELL" if copper_change < -1 else "HOLD"
                confidence = min(confidence + 0.1, 0.6)

        if "gold" in data:
            gold_change = data["gold"].get("change_pct", 0)
            reasoning_parts.append(f"Gold={gold_change:+.2f}%")
            if symbol == "USDCHF":
                signal = "SELL" if gold_change > 1 else "BUY" if gold_change < -1 else "HOLD"
                confidence = min(confidence + 0.1, 0.6)

        if "nikkei" in data:
            nikkei_change = data["nikkei"].get("change_pct", 0)
            reasoning_parts.append(f"Nikkei={nikkei_change:+.2f}%")
            if "JPY" in symbol:
                signal = "SELL" if nikkei_change > 1 else "BUY" if nikkei_change < -1 else "HOLD"
                confidence = min(confidence + 0.1, 0.6)

        if confidence == 0:
            confidence = 0.2

        return AnalystResult(
            analyst_name="fundamentals",
            symbol=symbol,
            timeframe=timeframe,
            signal=signal,
            confidence=round(confidence, 3),
            reasoning=" | ".join(reasoning_parts) if reasoning_parts else "Fundamentals neutral",
            data={"indicators": data, "data_source": "yfinance"},
        )

    def get_capabilities(self) -> list:
        return list(self._capabilities)
