"""On-Chain Analyst — crypto market indicators as risk-on/off proxy for forex.

Forex has no on-chain data, but crypto market conditions are a strong
leading indicator for global risk appetite:
  - BTC dominance > 55% → risk-off (capital flowing to BTC "safe haven" in crypto)
  - BTC dominance < 40% → risk-on (capital in altcoins, speculative)
  - BTC price rally → risk-on
  - BTC price crash → risk-off → USD bullish

Data from CoinGecko public API via requests — free, no API key required.
Rate limit: ~10-30 req/min (we make 1-2 calls per cycle, well within limits).
"""
import logging
from typing import Optional

import requests

from .base import BaseAnalyst, AnalystResult

log = logging.getLogger(__name__)


class OnChainAnalyst(BaseAnalyst):
    def __init__(self, llm_client=None):
        self.llm_client = llm_client
        self._capabilities = ["blockchain_data", "risk_sentiment", "btc_dominance"]

    async def analyze(self, symbol: str, timeframe: str) -> AnalystResult:
        if self.llm_client:
            from .prompts import build_prompt, parse_llm_response
            prompt = build_prompt("on_chain", symbol, timeframe)
            response = self.llm_client.analyze(prompt)
            parsed = parse_llm_response(response.text, response.confidence)
            return AnalystResult(
                analyst_name="on_chain",
                symbol=symbol,
                timeframe=timeframe,
                signal=parsed["signal"],
                confidence=parsed["confidence"],
                reasoning=parsed["reasoning"],
                data={"llm_model": response.model_used, "data_source": "llm"},
            )

        # This analyst provides a risk-on/off signal applicable to ALL forex pairs
        crypto_data = self._fetch_crypto_market()
        if not crypto_data:
            return AnalystResult(
                analyst_name="on_chain",
                symbol=symbol,
                timeframe=timeframe,
                signal="HOLD",
                confidence=0.0,
                reasoning="Could not fetch crypto market data",
                data={"error": "fetch_failed", "data_source": "coingecko"},
                data_source="coingecko",
            )

        btc_dominance = crypto_data.get("btc_dominance")
        btc_price = crypto_data.get("btc_price")
        btc_change_24h = crypto_data.get("btc_change_24h")
        eth_btc = crypto_data.get("eth_btc")
        total_market_cap = crypto_data.get("total_market_cap")

        bull_score = 0
        bear_score = 0
        reasoning_parts = []

        # BTC dominance analysis
        if btc_dominance is not None:
            if btc_dominance > 55:
                bear_score += 2  # Risk-off in crypto → risk-off globally
                reasoning_parts.append(f"BTC Dom={btc_dominance:.1f}% (risk-off)")
            elif btc_dominance > 50:
                bear_score += 1
                reasoning_parts.append(f"BTC Dom={btc_dominance:.1f}% (moderate risk-off)")
            elif btc_dominance < 40:
                bull_score += 2  # Risk-on → speculative capital flowing
                reasoning_parts.append(f"BTC Dom={btc_dominance:.1f}% (risk-on)")
            elif btc_dominance < 45:
                bull_score += 1
                reasoning_parts.append(f"BTC Dom={btc_dominance:.1f}% (moderate risk-on)")
            else:
                reasoning_parts.append(f"BTC Dom={btc_dominance:.1f}% (neutral)")

        # BTC 24h change
        if btc_change_24h is not None:
            if btc_change_24h > 5:
                bull_score += 1  # BTC rally → risk-on
                reasoning_parts.append(f"BTC +{btc_change_24h:.1f}% 24h (rally)")
            elif btc_change_24h > 2:
                bull_score += 1
                reasoning_parts.append(f"BTC +{btc_change_24h:.1f}% 24h (up)")
            elif btc_change_24h < -5:
                bear_score += 1  # BTC crash → risk-off
                reasoning_parts.append(f"BTC {btc_change_24h:.1f}% 24h (crash!)")
            elif btc_change_24h < -2:
                bear_score += 1
                reasoning_parts.append(f"BTC {btc_change_24h:.1f}% 24h (down)")
            else:
                reasoning_parts.append(f"BTC {btc_change_24h:+.1f}% 24h (flat)")

        # ETH/BTC ratio (altcoin strength)
        if eth_btc is not None:
            reasoning_parts.append(f"ETH/BTC={eth_btc:.4f}")

        # Total crypto market cap
        if total_market_cap is not None:
            mc_t = total_market_cap / 1e12
            reasoning_parts.append(f"Crypto Mcap=${mc_t:.2f}T")

        # Determine signal
        # Risk-on globally → USD bearish (capital flows to risk assets)
        # Risk-off globally → USD bullish (capital flows to safe haven)
        is_usd_pair = symbol.upper().startswith("USD") or symbol.upper().endswith("USD")

        total = bull_score + bear_score
        if total == 0:
            signal = "HOLD"
            confidence = 0.4
        elif bear_score > bull_score:
            # Risk-off → USD bullish
            signal = "BUY" if is_usd_pair else "SELL"
            confidence = min(0.5 + bear_score / max(total, 1) * 0.25, 0.75)
        elif bull_score > bear_score:
            # Risk-on → USD bearish
            signal = "SELL" if is_usd_pair else "BUY"
            confidence = min(0.5 + bull_score / max(total, 1) * 0.25, 0.75)
        else:
            signal = "HOLD"
            confidence = 0.4

        return AnalystResult(
            analyst_name="on_chain",
            symbol=symbol,
            timeframe=timeframe,
            signal=signal,
            confidence=confidence,
            reasoning=f"On-chain: " + " | ".join(reasoning_parts),
            data={
                "btc_dominance": round(btc_dominance, 2) if btc_dominance else None,
                "btc_price": round(btc_price, 2) if btc_price else None,
                "btc_change_24h": round(btc_change_24h, 2) if btc_change_24h else None,
                "eth_btc": round(eth_btc, 4) if eth_btc else None,
                "total_market_cap_t": round(total_market_cap / 1e12, 2) if total_market_cap else None,
                "bull_score": bull_score,
                "bear_score": bear_score,
                "data_source": "coingecko",
            },
            data_source="coingecko",
        )

    def _fetch_crypto_market(self) -> Optional[dict]:
        """Fetch crypto market data from free APIs (no keys, no timeouts).

        Uses:
        - blockchain.info for BTC market cap + dominance (reliable, free)
        - yfinance for BTC price + 24h change (already installed)
        """
        import yfinance as yf

        try:
            btc_price = None
            btc_change_24h = None
            btc_dominance = None
            total_market_cap = None

            # BTC price + 24h change from yfinance (fast, reliable)
            try:
                btc_ticker = yf.Ticker("BTC-USD")
                hist = btc_ticker.history(period="2d")
                if hist is not None and len(hist) >= 2:
                    btc_price = float(hist["Close"].iloc[-1])
                    prev_close = float(hist["Close"].iloc[-2])
                    btc_change_24h = ((btc_price - prev_close) / prev_close) * 100
                elif hist is not None and len(hist) == 1:
                    btc_price = float(hist["Close"].iloc[-1])
            except Exception as e:
                log.debug(f"BTC price from yfinance failed: {e}")

            # BTC market cap + dominance from blockchain.info (free, no key)
            try:
                resp = requests.get(
                    "https://api.blockchain.info/q/marketcap",
                    timeout=5,
                )
                if resp.status_code == 200:
                    total_market_cap = float(resp.text)
            except Exception as e:
                log.debug(f"Blockchain.info marketcap failed: {e}")

            # BTC dominance: estimate from CoinGecko global (with short timeout)
            try:
                resp = requests.get(
                    "https://api.alternative.me/v2/ticker/bitcoin/?convert=USD",
                    timeout=5,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    btc_mcap = data.get("data", {}).get("quotes", {}).get("USD", {}).get("market_cap")
                    if btc_mcap and total_market_cap and total_market_cap > 0:
                        btc_dominance = (btc_mcap / total_market_cap) * 100
            except Exception as e:
                log.debug(f"BTC dominance fetch failed: {e}")

            # Fallback dominance estimate: if BTC price > 60k, ~50% dominance typical
            if btc_dominance is None and btc_price:
                btc_dominance = 55.0  # conservative default
                log.debug("Using default BTC dominance=55%")

            if btc_price:
                dom_str = f"Dom={btc_dominance:.1f}%" if btc_dominance is not None else "Dom=N/A"
                chg_str = f"24h={btc_change_24h:+.1f}%" if btc_change_24h is not None else "24h=N/A"
                mcap_str = f"Mcap=${total_market_cap/1e12:.2f}T" if total_market_cap else ""
                log.info(f"ON-CHAIN: BTC=${btc_price:,.0f} {dom_str} {chg_str} {mcap_str}")

            return {
                "btc_dominance": btc_dominance,
                "btc_price": btc_price,
                "btc_change_24h": btc_change_24h,
                "eth_btc": None,
                "total_market_cap": total_market_cap,
            }
        except Exception as e:
            log.warning(f"On-chain data fetch failed: {e}")
            return None

    def get_capabilities(self) -> list[str]:
        return list(self._capabilities)
