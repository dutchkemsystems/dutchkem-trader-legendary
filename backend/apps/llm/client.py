"""LLM Client with provider chain: NVIDIA NIM → Ollama → Mock.

Priority:
1. NVIDIA NIM (cloud, fast, requires API key)
2. Ollama (local, free, requires ollama installed)
3. Mock (always works, returns placeholder)
"""

import os
from typing import Optional, Dict, Any
from .models import LLMResponse
from .mock_provider import MockProvider


class LLMClient:
    def __init__(self):
        self.nvidia_key = os.getenv("NVIDIA_API_KEY", "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")
        self.ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
        self.openrouter_key = os.getenv("OPENROUTER_API_KEY")
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
                self.providers.append(("ollama", self.ollama_url))
        except Exception:
            pass

        # 3. OpenRouter (if configured)
        if self.openrouter_key:
            self.providers.append(("openrouter", self.openrouter_key))

        self.mock_provider = MockProvider()
        self._primary = self.providers[0][0] if self.providers else "mock"

    @property
    def provider_status(self) -> Dict[str, Any]:
        """Return status of all providers."""
        return {
            "primary": self._primary,
            "available": [name for name, _ in self.providers],
            "mock_fallback": True,
            "nvidia_configured": bool(self.nvidia_key),
            "ollama_detected": any(name == "ollama" for name, _ in self.providers),
        }

    def analyze(
        self,
        prompt: str,
        output_schema: Optional[Dict[str, Any]] = None,
        model: str = "meta/llama-3.2-11b-vision-instruct",
    ) -> LLMResponse:
        """Analyze with automatic provider fallback."""
        if not self.providers:
            return self.mock_provider.analyze(prompt, output_schema)

        for provider_name, provider_config in self.providers:
            try:
                if provider_name == "nvidia_nim":
                    return self._call_nvidia_nim(prompt, output_schema, provider_config, model)
                elif provider_name == "ollama":
                    return self._call_ollama(prompt, output_schema, provider_config)
                elif provider_name == "openrouter":
                    return self._call_openrouter(prompt, output_schema, provider_config, model)
            except Exception as e:
                continue

        # All providers failed → mock fallback
        return self.mock_provider.analyze(prompt, output_schema)

    def _call_nvidia_nim(self, prompt, output_schema, api_key, model):
        """Call NVIDIA NIM API (OpenAI-compatible endpoint)."""
        import httpx

        # NVIDIA NIM uses OpenAI-compatible API
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
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        text = data["choices"][0]["message"]["content"]
        return LLMResponse(text=text, confidence=0.9, model_used=f"nvidia_nim/{model}")

    def _call_ollama(self, prompt, output_schema, base_url):
        """Call local Ollama instance."""
        import httpx

        resp = httpx.post(
            f"{base_url}/api/generate",
            json={"model": "phi3:3.8b", "prompt": prompt, "stream": False},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        text = data.get("response", "")
        return LLMResponse(text=text, confidence=0.8, model_used="ollama/phi3")

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
