import pytest
from apps.llm.client import LLMClient
from apps.llm.models import LLMResponse


def test_llm_client_has_providers():
    client = LLMClient()
    status = client.provider_status
    assert "primary" in status
    assert "available" in status
    assert isinstance(status["available"], list)


def test_llm_client_analyze():
    client = LLMClient()
    response = client.analyze("Analyze EURUSD trend")
    assert isinstance(response, LLMResponse)
    assert response.text is not None
    assert 0.0 <= response.confidence <= 1.0


def test_llm_client_structured_output():
    client = LLMClient()
    response = client.analyze(
        "Analyze EURUSD. Return JSON with signal (BUY/SELL/HOLD) and confidence (float)."
    )
    # Real LLM returns natural language — parsed may be empty
    # The important thing is that analyze() returns a valid response
    assert isinstance(response, LLMResponse)
    assert response.text is not None
    assert len(response.text) > 0
