"""LLM Client with provider chain: NVIDIA NIM → Ollama → Mock.

Priority:
1. NVIDIA NIM (cloud, fast, requires API key)
2. Ollama (local, free, requires ollama installed)
3. Mock (always works, returns placeholder)

Trading-specific features:
- Structured signal analysis prompts
- Multi-model consensus via Ollama
- Model selection by task type (analysis, debate, risk)
"""

import asyncio
import os
import json
import logging
import re
import time
import threading
from typing import Optional, Dict, Any, List
from .models import LLMResponse
from .mock_provider import MockProvider

logger = logging.getLogger(__name__)


class RateLimiter:
    """Simple token-bucket rate limiter. Thread-safe."""

    def __init__(self, max_calls: int = 30, period_seconds: float = 60.0):
        self.max_calls = max_calls
        self.period = period_seconds
        self._timestamps: List[float] = []
        self._lock = threading.Lock()

    def wait(self):
        """Block until a request slot is available."""
        sleep_for = 0.0
        with self._lock:
            now = time.monotonic()
            # Purge timestamps outside the window
            self._timestamps = [t for t in self._timestamps if now - t < self.period]
            if len(self._timestamps) >= self.max_calls:
                sleep_for = self.period - (now - self._timestamps[0]) + 0.1
            self._timestamps.append(time.monotonic())
        # Sleep OUTSIDE the lock so other threads aren't blocked
        if sleep_for > 0:
            logger.info("Rate limit: sleeping %.1fs", sleep_for)
            time.sleep(sleep_for)

# ── Trading-specific prompt templates ──

TRADING_ANALYSIS_PROMPT = """You are a professional forex technical analyst. Analyze the following data and provide a trading signal.

Symbol: {symbol}
Timeframe: {timeframe}
Current Price: {price}

Technical Indicators:
- RSI: {rsi}
- MACD Histogram: {macd_hist}
- ADX: {adx} (+DI: {plus_di}, -DI: {minus_di})
- ATR: {atr}
- EMA21: {ema21} | SMA50: {sma50}
- BB Width: {bb_width}
- Volume Ratio: {vol_ratio}
- Ichimoku: Tenkan={tenkan}, Kijun={kijun}, SenkouA={senkou_a}, SenkouB={senkou_b}

Recent price action: {price_action}

Provide your analysis as JSON with these fields:
- signal: "BUY" or "SELL" or "HOLD"
- confidence: 0.0 to 1.0
- reasoning: brief explanation (1-2 sentences)
- key_levels: {{"support": number, "resistance": number}}

Respond with ONLY the JSON object, no extra text."""

DEBATE_BULL_PROMPT = """You are a BULLISH market researcher arguing that {symbol} will go UP.

Market Data:
- Price: {price}
- RSI: {rsi} | MACD: {macd_hist} | ADX: {adx}
- Trend: EMA21={ema21}, SMA50={sma50}
- Volume: {vol_ratio}x average
- Ichimoku: Cloud={cloud_position}

Past rounds: {past_rounds}

Make a strong bullish case. Be specific about technical levels and catalysts.
Provide your argument as JSON:
- confidence: 0.0 to 1.0 (how confident are you?)
- reasoning: your bullish argument (2-3 sentences)
- key_evidence: ["evidence1", "evidence2"]

Respond with ONLY the JSON object."""

DEBATE_BEAR_PROMPT = """You are a BEARISH market researcher arguing that {symbol} will go DOWN.

Market Data:
- Price: {price}
- RSI: {rsi} | MACD: {macd_hist} | ADX: {adx}
- Trend: EMA21={ema21}, SMA50={sma50}
- Volume: {vol_ratio}x average
- Ichimoku: Cloud={cloud_position}

Past rounds: {past_rounds}

Make a strong bearish case. Be specific about technical levels and catalysts.
Provide your argument as JSON:
- confidence: 0.0 to 1.0 (how confident are you?)
- reasoning: your bearish argument (2-3 sentences)
- key_evidence: ["evidence1", "evidence2"]

Respond with ONLY the JSON object."""

RISK_ASSESSMENT_PROMPT = """You are a risk analyst for a trading system. Evaluate this potential trade.

Symbol: {symbol}
Direction: {direction}
Score: {score}
ATR: {atr}
Volatility: {volatility}
Current positions: {current_positions}/{max_positions}
Account Balance: ${balance}
Drawdown: {drawdown_pct}%

Assess the risk. Provide JSON:
- approved: true or false
- risk_level: "low" or "medium" or "high"
- reasoning: brief risk assessment (1-2 sentences)
- suggested_position_size_pct: suggested % of equity to risk (0.5 to 5.0)

Respond with ONLY the JSON object."""


class LLMClient:
    def __init__(self):
        self.nvidia_key = os.getenv("NVIDIA_API_KEY", "")
        self.ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
        # Storage-optimized: use qwen2.5:7b for all tasks (only 4.7GB model available)
        # qwen2:0.5b serves as ultra-fast fallback for lightweight tasks
        self.ollama_analysis_model = os.getenv("OLLAMA_ANALYSIS_MODEL", "qwen2.5:7b")
        self.ollama_debate_model = os.getenv("OLLAMA_DEBATE_MODEL", "qwen2.5:7b")
        self.ollama_risk_model = os.getenv("OLLAMA_RISK_MODEL", "qwen2.5:7b")
        self.openrouter_key = os.getenv("OPENROUTER_API_KEY")
        self._available_ollama_models: List[str] = []

        # Rate limiting + retry config
        self._rate_limiter = RateLimiter(max_calls=120, period_seconds=60.0)
        self._max_retries = 1  # per provider (reduced to avoid thread pool saturation)
        self._backoff_base = 1.0  # seconds, exponential: 1s, 2s, 4s

        # Request counter for monitoring
        self._request_count = 0
        self._error_count = 0

        self._init_providers()

    def _init_providers(self):
        """Build provider chain: NVIDIA NIM → Ollama → Mock."""
        self.providers = []

        # 1. NVIDIA NIM (primary — cloud, fast)
        if self.nvidia_key:
            self.providers.append(("nvidia_nim", self.nvidia_key))

        # 2. Ollama (fallback — local, free)
        try:
            import httpx
            resp = httpx.get(f"{self.ollama_url}/api/tags", timeout=3)
            if resp.status_code == 200:
                models_data = resp.json().get("models", [])
                self._available_ollama_models = [m["name"] for m in models_data]
                if self._available_ollama_models:
                    self.providers.append(("ollama", self.ollama_url))
                    logger.info("Ollama detected with models: %s", self._available_ollama_models)
        except Exception as e:
            logger.debug("Ollama not available: %s", e)

        # 3. OpenRouter (if configured)
        if self.openrouter_key:
            self.providers.append(("openrouter", self.openrouter_key))

        self.mock_provider = MockProvider()
        self._primary = self.providers[0][0] if self.providers else "mock"

    def _pick_ollama_model(self, task: str = "analysis") -> str:
        """Pick best available Ollama model for a task."""
        preferred = {
            "analysis": self.ollama_analysis_model,
            "debate": self.ollama_debate_model,
            "risk": self.ollama_risk_model,
        }
        target = preferred.get(task, self.ollama_analysis_model)

        # Check if target is available (exact or prefix match)
        for available in self._available_ollama_models:
            if available == target or available.startswith(target.split(":")[0]):
                return available

        # Fallback: prefer qwen2.5:7b, then any available, then qwen2:0.5b
        if self._available_ollama_models:
            # Prefer the 7b model for quality
            for m in self._available_ollama_models:
                if "qwen2.5" in m and "7b" in m:
                    return m
            return self._available_ollama_models[0]

        return "qwen2:0.5b"

    @property
    def provider_status(self) -> Dict[str, Any]:
        """Return status of all providers."""
        return {
            "primary": self._primary,
            "available": [name for name, _ in self.providers],
            "mock_fallback": True,
            "nvidia_configured": bool(self.nvidia_key),
            "ollama_detected": any(name == "ollama" for name, _ in self.providers),
            "ollama_models": self._available_ollama_models,
            "ollama_analysis_model": self.ollama_analysis_model,
            "ollama_debate_model": self.ollama_debate_model,
            "ollama_risk_model": self.ollama_risk_model,
            "request_count": self._request_count,
            "error_count": self._error_count,
            "rate_limit": f"{self._rate_limiter.max_calls}/{self._rate_limiter.period}s",
        }

    def analyze(
        self,
        prompt: str,
        output_schema: Optional[Dict[str, Any]] = None,
        model: str = "meta/llama-3.2-11b-vision-instruct",
        task: str = "analysis",
    ) -> LLMResponse:
        """Analyze with automatic provider fallback, retry, and backoff."""
        if not self.providers:
            return self.mock_provider.analyze(prompt, output_schema)

        for provider_name, provider_config in self.providers:
            last_error = None
            for attempt in range(1 + self._max_retries):
                try:
                    # Rate limit before each request
                    self._rate_limiter.wait()
                    self._request_count += 1

                    if provider_name == "nvidia_nim":
                        return self._call_nvidia_nim(prompt, output_schema, provider_config, model)
                    elif provider_name == "ollama":
                        ollama_model = self._pick_ollama_model(task)
                        return self._call_ollama(prompt, output_schema, provider_config, ollama_model)
                    elif provider_name == "openrouter":
                        return self._call_openrouter(prompt, output_schema, provider_config, model)
                except Exception as e:
                    last_error = e
                    self._error_count += 1
                    if attempt < self._max_retries:
                        backoff = self._backoff_base * (2 ** attempt)
                        logger.warning("Provider %s attempt %d failed: %s — retrying in %.1fs",
                                       provider_name, attempt + 1, e, backoff)
                        time.sleep(backoff)
                    else:
                        logger.debug("Provider %s exhausted %d retries: %s", provider_name, self._max_retries + 1, e)

        # All providers failed → mock fallback
        logger.warning("All LLM providers failed (errors=%d), using mock", self._error_count)
        return self.mock_provider.analyze(prompt, output_schema)

    async def analyze_async(
        self,
        prompt: str,
        output_schema: Optional[Dict[str, Any]] = None,
        model: str = "meta/llama-3.2-11b-vision-instruct",
        task: str = "analysis",
    ) -> LLMResponse:
        """Non-blocking version of analyze — runs in thread to avoid blocking event loop."""
        return await asyncio.to_thread(self.analyze, prompt, output_schema, model, task)

    def analyze_trading_signal(self, symbol: str, timeframe: str, indicators: Dict[str, Any], price_action: str = "") -> LLMResponse:
        """Structured trading signal analysis."""
        prompt = TRADING_ANALYSIS_PROMPT.format(
            symbol=symbol,
            timeframe=timeframe,
            price=indicators.get("close", 0),
            rsi=indicators.get("rsi", "N/A"),
            macd_hist=indicators.get("macd_hist", "N/A"),
            adx=indicators.get("adx", "N/A"),
            plus_di=indicators.get("plus_di", "N/A"),
            minus_di=indicators.get("minus_di", "N/A"),
            atr=indicators.get("atr", "N/A"),
            ema21=indicators.get("ema_21", "N/A"),
            sma50=indicators.get("sma_50", "N/A"),
            bb_width=indicators.get("bb_width", "N/A"),
            vol_ratio=indicators.get("vol_ratio", "N/A"),
            tenkan=indicators.get("tenkan", "N/A"),
            kijun=indicators.get("kijun", "N/A"),
            senkou_a=indicators.get("senkou_a", "N/A"),
            senkou_b=indicators.get("senkou_b", "N/A"),
            price_action=price_action,
        )
        response = self.analyze(prompt, task="analysis")
        parsed = self._try_parse_json(response.text)
        if parsed:
            response.parsed = parsed
        return response

    def analyze_debate(self, symbol: str, stance: str, indicators: Dict[str, Any], past_rounds: str = "") -> LLMResponse:
        """Run debate argument for bull or bear."""
        template = DEBATE_BULL_PROMPT if stance == "BULL" else DEBATE_BEAR_PROMPT
        prompt = template.format(
            symbol=symbol,
            price=indicators.get("close", 0),
            rsi=indicators.get("rsi", "N/A"),
            macd_hist=indicators.get("macd_hist", "N/A"),
            adx=indicators.get("adx", "N/A"),
            ema21=indicators.get("ema_21", "N/A"),
            sma50=indicators.get("sma_50", "N/A"),
            vol_ratio=indicators.get("vol_ratio", "N/A"),
            cloud_position="above" if indicators.get("close", 0) > indicators.get("senkou_a", 0) else "below",
            past_rounds=past_rounds or "None (first round)",
        )
        response = self.analyze(prompt, task="debate")
        parsed = self._try_parse_json(response.text)
        if parsed:
            response.parsed = parsed
        return response

    def assess_risk(self, symbol: str, direction: str, score: float, atr: float,
                    volatility: float, current_positions: int, max_positions: int,
                    balance: float, drawdown_pct: float) -> LLMResponse:
        """Risk assessment for a potential trade."""
        prompt = RISK_ASSESSMENT_PROMPT.format(
            symbol=symbol,
            direction=direction,
            score=score,
            atr=atr,
            volatility=volatility,
            current_positions=current_positions,
            max_positions=max_positions,
            balance=balance,
            drawdown_pct=drawdown_pct,
        )
        response = self.analyze(prompt, task="risk")
        parsed = self._try_parse_json(response.text)
        if parsed:
            response.parsed = parsed
        return response

    def get_multi_model_consensus(self, symbol: str, indicators: Dict[str, Any]) -> Dict[str, Any]:
        """Run multiple Ollama models and take consensus."""
        if not self._available_ollama_models:
            return {"consensus": "HOLD", "confidence": 0, "models_agreed": 0, "models_total": 0, "model_signals": []}

        signals = []
        prompt = TRADING_ANALYSIS_PROMPT.format(
            symbol=symbol,
            timeframe="H1",
            price=indicators.get("close", 0),
            rsi=indicators.get("rsi", "N/A"),
            macd_hist=indicators.get("macd_hist", "N/A"),
            adx=indicators.get("adx", "N/A"),
            plus_di=indicators.get("plus_di", "N/A"),
            minus_di=indicators.get("minus_di", "N/A"),
            atr=indicators.get("atr", "N/A"),
            ema21=indicators.get("ema_21", "N/A"),
            sma50=indicators.get("sma_50", "N/A"),
            bb_width=indicators.get("bb_width", "N/A"),
            vol_ratio=indicators.get("vol_ratio", "N/A"),
            tenkan=indicators.get("tenkan", "N/A"),
            kijun=indicators.get("kijun", "N/A"),
            senkou_a=indicators.get("senkou_a", "N/A"),
            senkou_b=indicators.get("senkou_b", "N/A"),
            price_action="",
        )

        # Query up to 3 models
        for model_name in self._available_ollama_models[:3]:
            try:
                import httpx
                resp = httpx.post(
                    f"{self.ollama_url}/api/generate",
                    json={"model": model_name, "prompt": prompt, "stream": False},
                    timeout=15,
                )
                resp.raise_for_status()
                text = resp.json().get("response", "")
                parsed = self._try_parse_json(text)
                if parsed:
                    signals.append({
                        "model": model_name,
                        "signal": parsed.get("signal", "HOLD"),
                        "confidence": parsed.get("confidence", 0.5),
                        "reasoning": parsed.get("reasoning", ""),
                    })
                else:
                    signals.append({
                        "model": model_name,
                        "signal": "HOLD",
                        "confidence": 0.5,
                        "reasoning": text[:200],
                    })
            except Exception as e:
                logger.debug("Model %s failed: %s", model_name, e)

        if not signals:
            return {"consensus": "HOLD", "confidence": 0, "models_agreed": 0, "models_total": 0, "model_signals": []}

        # Count votes
        buy_count = sum(1 for s in signals if s["signal"] == "BUY")
        sell_count = sum(1 for s in signals if s["signal"] == "SELL")
        hold_count = sum(1 for s in signals if s["signal"] == "HOLD")
        total = len(signals)

        if buy_count > sell_count and buy_count > hold_count:
            consensus = "BUY"
            agreed = buy_count
        elif sell_count > buy_count and sell_count > hold_count:
            consensus = "SELL"
            agreed = sell_count
        else:
            consensus = "HOLD"
            agreed = hold_count

        avg_conf = sum(s["confidence"] for s in signals) / total

        return {
            "consensus": consensus,
            "confidence": round(avg_conf, 3),
            "models_agreed": agreed,
            "models_total": total,
            "model_signals": signals,
        }

    def _try_parse_json(self, text: str) -> Optional[Dict]:
        """Try to extract JSON from LLM response text."""
        # Try direct parse
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            pass

        # Try to find JSON block in text
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        return None

    def _call_nvidia_nim(self, prompt, output_schema, api_key, model):
        """Call NVIDIA NIM API (OpenAI-compatible endpoint)."""
        import httpx

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "max_tokens": 1024,
        }

        resp = httpx.post(
            "https://integrate.api.nvidia.com/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        text = data["choices"][0]["message"]["content"]
        return LLMResponse(text=text, confidence=0.9, model_used=f"nvidia_nim/{model}")

    def _call_ollama(self, prompt, output_schema, base_url, model=None):
        """Call local Ollama instance."""
        import httpx

        if model is None:
            model = self._pick_ollama_model("analysis")

        resp = httpx.post(
            f"{base_url}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        text = data.get("response", "")
        used_model = data.get("model", model)
        return LLMResponse(text=text, confidence=0.8, model_used=f"ollama/{used_model}")

    def _call_openrouter(self, prompt, output_schema, api_key, model):
        """Call OpenRouter API."""
        import httpx

        resp = httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        text = data["choices"][0]["message"]["content"]
        return LLMResponse(text=text, confidence=0.85, model_used=model)
