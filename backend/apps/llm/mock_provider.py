from .models import LLMResponse


class MockProvider:
    def analyze(self, prompt, output_schema=None):
        """Return error response — no LLM available. Never generate fake signals."""
        return LLMResponse(
            text="No LLM provider available. Analysis requires NVIDIA NIM, Ollama, or OpenRouter.",
            confidence=0.0,
            parsed={"error": "no_llm_available", "signal": "HOLD"},
            model_used="none",
            tokens_used=0,
        )
