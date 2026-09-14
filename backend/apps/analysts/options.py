"""Options Analyst — SPY/QQQ options chain for market sentiment proxy.

Forex pairs don't have options, but equity options on SPY/QQQ give strong
market-wide signals that correlate with forex movements:
  - Put/Call ratio > 1.0 → bearish sentiment → risk-off → USD bullish
  - Put/Call ratio < 0.7 → bullish sentiment → risk-on → USD bearish
  - High IV → market uncertainty → risk-off
  - Low IV → market complacency → risk-on

All data via yfinance — free, no API key required.
"""
import logging
from typing import Optional

import yfinance as yf

from .base import BaseAnalyst, AnalystResult

log = logging.getLogger(__name__)

# Which ETF options to scan as market sentiment proxies
_PROXY_ETFS = ["SPY", "QQQ", "IWM"]  # S&P 500, Nasdaq, Russell 2000


class OptionsAnalyst(BaseAnalyst):
    def __init__(self, llm_client=None):
        self.llm_client = llm_client
        self._capabilities = ["implied_volatility", "put_call_ratio", "greeks_analysis"]

    async def analyze(self, symbol: str, timeframe: str) -> AnalystResult:
        if self.llm_client:
            from .prompts import build_prompt, parse_llm_response
            prompt = build_prompt("options", symbol, timeframe)
            response = self.llm_client.analyze(prompt)
            parsed = parse_llm_response(response.text, response.confidence)
            return AnalystResult(
                analyst_name="options",
                symbol=symbol,
                timeframe=timeframe,
                signal=parsed["signal"],
                confidence=parsed["confidence"],
                reasoning=parsed["reasoning"],
                data={"llm_model": response.model_used, "data_source": "llm"},
            )

        options_data = self._fetch_options()
        if not options_data:
            return AnalystResult(
                analyst_name="options",
                symbol=symbol,
                timeframe=timeframe,
                signal="HOLD",
                confidence=0.0,
                reasoning="Could not fetch options chain data",
                data={"error": "fetch_failed", "data_source": "yfinance"},
                data_source="yfinance",
            )

        # Aggregate signals across ETFs
        total_put_vol = 0
        total_call_vol = 0
        avg_iv = 0
        iv_count = 0
        etf_details = []

        for etf, chain in options_data.items():
            pcr = chain.get("put_call_ratio", 1.0)
            iv = chain.get("avg_iv", 0.2)
            call_vol = chain.get("call_volume", 0)
            put_vol = chain.get("put_volume", 0)
            total_call_vol += call_vol
            total_put_vol += put_vol
            avg_iv += iv
            iv_count += 1
            etf_details.append(f"{etf}: PCR={pcr:.2f} IV={iv:.1%} vol={call_vol+put_vol}")

        avg_pcr = total_put_vol / max(total_call_vol, 1)
        avg_iv = avg_iv / max(iv_count, 1)

        # Signal logic
        bull_score = 0
        bear_score = 0
        reasoning_parts = []

        # Put/Call ratio (lowered thresholds for more directional signals)
        if avg_pcr > 1.0:
            bear_score += 2
            reasoning_parts.append(f"PCR={avg_pcr:.2f} (very bearish)")
        elif avg_pcr > 0.9:
            bear_score += 1
            reasoning_parts.append(f"PCR={avg_pcr:.2f} (bearish)")
        elif avg_pcr < 0.7:
            bull_score += 2
            reasoning_parts.append(f"PCR={avg_pcr:.2f} (very bullish)")
        elif avg_pcr < 0.8:
            bull_score += 1
            reasoning_parts.append(f"PCR={avg_pcr:.2f} (bullish)")
        else:
            reasoning_parts.append(f"PCR={avg_pcr:.2f} (neutral)")

        # Implied Volatility
        if avg_iv > 0.35:
            bear_score += 1
            reasoning_parts.append(f"IV={avg_iv:.1%} (high uncertainty)")
        elif avg_iv < 0.15:
            bull_score += 1
            reasoning_parts.append(f"IV={avg_iv:.1%} (low volatility)")
        else:
            reasoning_parts.append(f"IV={avg_iv:.1%}")

        # Volume skew (put volume vs call volume)
        if total_put_vol > total_call_vol * 1.5:
            bear_score += 1
            reasoning_parts.append(f"Put vol >> Call vol (hedging demand)")
        elif total_call_vol > total_put_vol * 1.5:
            bull_score += 1
            reasoning_parts.append(f"Call vol >> Put vol (upside demand)")

        # Determine signal
        # For forex: equity bearishness = USD bullish (safe haven)
        is_usd_pair = symbol.upper().startswith("USD") or symbol.upper().endswith("USD")

        total = bull_score + bear_score
        if total == 0:
            signal = "HOLD"
            confidence = 0.4
        elif bear_score > bull_score:
            # Equity bearish → risk-off → USD bullish
            signal = "BUY" if is_usd_pair else "SELL"
            confidence = min(0.5 + bear_score / max(total, 1) * 0.3, 0.8)
        elif bull_score > bear_score:
            # Equity bullish → risk-on → USD bearish
            signal = "SELL" if is_usd_pair else "BUY"
            confidence = min(0.5 + bull_score / max(total, 1) * 0.3, 0.8)
        else:
            signal = "HOLD"
            confidence = 0.45

        return AnalystResult(
            analyst_name="options",
            symbol=symbol,
            timeframe=timeframe,
            signal=signal,
            confidence=confidence,
            reasoning=f"Options: " + " | ".join(reasoning_parts),
            data={
                "put_call_ratio": round(avg_pcr, 3),
                "avg_iv": round(avg_iv, 4),
                "total_call_volume": total_call_vol,
                "total_put_volume": total_put_vol,
                "etf_details": etf_details,
                "data_source": "yfinance",
            },
            data_source="yfinance",
        )

    def _fetch_options(self) -> dict[str, dict]:
        """Fetch options chain data for proxy ETFs."""
        result = {}
        for etf in _PROXY_ETFS:
            try:
                ticker = yf.Ticker(etf)
                expirations = ticker.options
                if not expirations:
                    continue

                # Use nearest expiration
                chain = ticker.option_chain(expirations[0])
                calls = chain.calls
                puts = chain.puts

                call_vol = int(calls["volume"].sum()) if calls["volume"].notna().any() else 0
                put_vol = int(puts["volume"].sum()) if puts["volume"].notna().any() else 0

                call_iv = float(calls["impliedVolatility"].median()) if calls["impliedVolatility"].notna().any() else 0.2
                put_iv = float(puts["impliedVolatility"].median()) if puts["impliedVolatility"].notna().any() else 0.2

                pcr = put_vol / max(call_vol, 1)
                avg_iv = (call_iv + put_iv) / 2

                result[etf] = {
                    "put_call_ratio": pcr,
                    "avg_iv": avg_iv,
                    "call_volume": call_vol,
                    "put_volume": put_vol,
                    "expiration": expirations[0],
                }
                log.info(f"OPTIONS {etf}: PCR={pcr:.2f} IV={avg_iv:.1%} call_vol={call_vol} put_vol={put_vol}")
            except Exception as e:
                log.debug(f"Options fetch for {etf} failed: {e}")
        return result

    def get_capabilities(self) -> list[str]:
        return list(self._capabilities)
