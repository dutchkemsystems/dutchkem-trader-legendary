import pytest
from apps.llm.client import LLMClient
from apps.llm.models import LLMResponse


def test_llm_client_mock_mode():
    client = LLMClient()
    assert client.mock_mode is True


def test_llm_client_analyze():
    client = LLMClient()
    response = client.analyze("Analyze EURUSD trend")
    assert isinstance(response, LLMResponse)
    assert response.text is not None
    assert 0.0 <= response.confidence <= 1.0


def test_llm_client_structured_output():
    client = LLMClient()
    response = client.analyze(
        "Analyze EURUSD",
        output_schema={"signal": "BUY|SELL|HOLD", "confidence": "float"}
    )
    assert "signal" in response.parsed
    assert response.parsed["signal"] in ("BUY", "SELL", "HOLD")
