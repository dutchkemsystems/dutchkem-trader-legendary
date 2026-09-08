import os
from typing import Optional, Dict, Any
from .models import LLMResponse
from .mock_provider import MockProvider


class LLMClient:
    def __init__(self):
        self.openai_key = os.getenv("OPENAI_API_KEY")
        self.anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        self.google_key = os.getenv("GOOGLE_API_KEY")
        self.ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
        self.openrouter_key = os.getenv("OPENROUTER_API_KEY")
        self.mock_mode = not any(
            [self.openai_key, self.anthropic_key, self.google_key, self.openrouter_key]
        )
        self._init_providers()

    def _init_providers(self):
        self.providers = []
        if not self.mock_mode:
            try:
                import httpx

                resp = httpx.get(f"{self.ollama_url}/api/tags", timeout=2)
                if resp.status_code == 200:
                    self.providers.append(("ollama", self.ollama_url))
            except Exception:
                pass
            if self.openrouter_key:
                self.providers.append(("openrouter", self.openrouter_key))
        self.mock_provider = MockProvider()

    def analyze(
        self,
        prompt: str,
        output_schema: Optional[Dict[str, Any]] = None,
        model: str = "gpt-4",
    ) -> LLMResponse:
        if self.mock_mode or not self.providers:
            return self.mock_provider.analyze(prompt, output_schema)

        for provider_name, provider_config in self.providers:
            try:
                if provider_name == "ollama":
                    return self._call_ollama(prompt, output_schema, provider_config)
                elif provider_name == "openrouter":
                    return self._call_openrouter(
                        prompt, output_schema, provider_config, model
                    )
            except Exception:
                continue

        return self.mock_provider.analyze(prompt, output_schema)

    def _call_ollama(self, prompt, output_schema, base_url):
        import httpx

        resp = httpx.post(
            f"{base_url}/api/generate",
            json={"model": "llama3.2", "prompt": prompt, "stream": False},
            timeout=30,
        )
        data = resp.json()
        text = data.get("response", "")
        return LLMResponse(text=text, confidence=0.8, model_used="ollama")

    def _call_openrouter(self, prompt, output_schema, api_key, model):
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
        data = resp.json()
        text = data["choices"][0]["message"]["content"]
        return LLMResponse(text=text, confidence=0.85, model_used=model)
