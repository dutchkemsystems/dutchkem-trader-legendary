"""
Fundamentals Analyst — Uses yfinance for currency-related fundamentals.
Fetches central bank rates, bond yields, and economic indicators.
No API key required.
"""
import asyncio
import logging
from datetime import datetime, timezone
from .base import BaseAnalyst, AnalystResult

log = logging.getLogger("fundamentals_analyst")

# Map forex pairs to valid yfinance tickers
PAIR_FUNDAMENTALS = {
    "EURUSD": {"dxy": "DX-Y.NYB", "us10y": "^TNX", "gold": "GC=F"},
    "GBPUSD": {"dxy": "DX-Y.NYB", "us10y": "^TNX", "gold": "GC=F"},
    "USDCHF": {"dxy": "DX-Y.NYB", "us10y": "^TNX", "gold": "GC=F"},
    "AUDUSD": {"dxy": "DX-Y.NYB", "us10y": "^TNX", "copper": "HG=F", "gold": "GC=F"},
    "NZDUSD": {"dxy": "DX-Y.NYB", "us10y": "^TNX", "gold": "GC=F"},
    "USDCAD": {"dxy": "DX-Y.NYB", "us10y": "^TNX", "oil": "CL=F", "gold": "GC=F"},
    "EURGBP": {"dxy": "DX-Y.NYB", "gold": "GC=F"},
    "EURJPY": {"dxy": "DX-Y.NYB", "us10y": "^TNX", "nikkei": "^N225", "gold": "GC=F"},
    "GBPJPY": {"dxy": "DX-Y.NYB", "us10y": "^TNX", "nikkei": "^N225", "gold": "GC=F"},
    "USDJPY": {"dxy": "DX-Y.NYB", "us10y": "^TNX", "nikkei": "^N225", "gold": "GC=F"},
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
                response = await asyncio.to_thread(self.llm_client.analyze, prompt)
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

        # ── DXY Direction (works for ALL pairs) ──
        if "dxy" in data:
            dxy_val = data["dxy"]["value"]
            dxy_change = data["dxy"].get("change_pct", 0)
            reasoning_parts.append(f"DXY={dxy_val:.1f} ({dxy_change:+.2f}%)")
            is_usd_first = symbol.startswith("USD")
            if dxy_change > 0.15:
                signal = "SELL" if is_usd_first else "BUY"
                confidence = min(confidence + 0.20, 0.7)
                reasoning_parts.append("DXY rising → USD strengthening")
            elif dxy_change < -0.15:
                signal = "BUY" if is_usd_first else "SELL"
                confidence = min(confidence + 0.20, 0.7)
                reasoning_parts.append("DXY falling → USD weakening")

        # ── US 10Y Yield ──
        if "us10y" in data:
            us10y = data["us10y"]["value"]
            reasoning_parts.append(f"US10Y={us10y:.2f}%")
            if us10y > 4.0:
                if signal == "HOLD":
                    signal = "BUY" if symbol.startswith("USD") else "SELL"
                confidence = min(confidence + 0.12, 0.7)
                reasoning_parts.append("High US yields → capital flows to USD")
            elif us10y < 4.0:
                if signal == "HOLD":
                    signal = "SELL" if symbol.startswith("USD") else "BUY"
                confidence = min(confidence + 0.12, 0.7)
                reasoning_parts.append("Low US yields → capital flows from USD")

        # ── Gold (safe haven — inverse to risk appetite) ──
        if "gold" in data:
            gold_change = data["gold"].get("change_pct", 0)
            reasoning_parts.append(f"Gold={gold_change:+.2f}%")
            if gold_change > 0.5:
                if symbol == "USDCHF":
                    signal = "SELL"
                    confidence = min(confidence + 0.15, 0.7)
                elif symbol == "XAUUSD":
                    signal = "BUY"
                    confidence = min(confidence + 0.15, 0.7)
                reasoning_parts.append("Gold rising → risk-off sentiment")
            elif gold_change < -0.5:
                if symbol == "USDCHF":
                    signal = "BUY"
                    confidence = min(confidence + 0.15, 0.7)
                reasoning_parts.append("Gold falling → risk-on sentiment")

        # ── Oil (CAD correlation) ──
        if "oil" in data:
            oil_change = data["oil"].get("change_pct", 0)
            reasoning_parts.append(f"Oil={oil_change:+.2f}%")
            if symbol == "USDCAD":
                signal = "SELL" if oil_change > 0.5 else "BUY" if oil_change < -0.5 else signal
                confidence = min(confidence + 0.12, 0.7)

        # ── Copper (AUD correlation) ──
        if "copper" in data:
            copper_change = data["copper"].get("change_pct", 0)
            reasoning_parts.append(f"Copper={copper_change:+.2f}%")
            if symbol == "AUDUSD":
                signal = "BUY" if copper_change > 0.5 else "SELL" if copper_change < -0.5 else signal
                confidence = min(confidence + 0.12, 0.7)

        # ── Nikkei (JPY risk sentiment) ──
        if "nikkei" in data:
            nikkei_change = data["nikkei"].get("change_pct", 0)
            reasoning_parts.append(f"Nikkei={nikkei_change:+.2f}%")
            if "JPY" in symbol:
                signal = "SELL" if nikkei_change > 0.5 else "BUY" if nikkei_change < -0.5 else signal
                confidence = min(confidence + 0.12, 0.7)

        if confidence == 0:
            confidence = 0.15

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
