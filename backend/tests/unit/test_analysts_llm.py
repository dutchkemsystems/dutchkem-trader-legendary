import pytest
from apps.llm.client import LLMClient
from apps.llm.models import LLMResponse
from apps.analysts.prompts import parse_llm_response, build_prompt, ANALYST_PROMPTS
from apps.analysts.base import AnalystResult


# --- Prompt and Parser Tests ---

def test_parse_llm_response_buy():
    text = "SIGNAL: BUY\nCONFIDENCE: 0.85\nREASONING: Strong bullish momentum with RSI at 72."
    result = parse_llm_response(text, 0.7)
    assert result['signal'] == 'BUY'
    assert result['confidence'] == 0.85
    assert 'bullish momentum' in result['reasoning']


def test_parse_llm_response_sell():
    text = "SIGNAL: SELL\nCONFIDENCE: 0.72\nREASONING: Bearish divergence on MACD."
    result = parse_llm_response(text, 0.7)
    assert result['signal'] == 'SELL'
    assert result['confidence'] == 0.72


def test_parse_llm_response_hold():
    text = "SIGNAL: HOLD\nCONFIDENCE: 0.55\nREASONING: Mixed signals, waiting for confirmation."
    result = parse_llm_response(text, 0.7)
    assert result['signal'] == 'HOLD'
    assert result['confidence'] == 0.55


def test_parse_llm_response_fallback_defaults():
    text = "The market looks uncertain with mixed signals."
    result = parse_llm_response(text, 0.6)
    assert result['signal'] == 'HOLD'
    assert result['confidence'] == 0.6
    assert result['reasoning'] == text


def test_parse_llm_response_case_insensitive():
    text = "signal: buy\nconfidence: 0.9\nreasoning: Testing case."
    result = parse_llm_response(text)
    assert result['signal'] == 'BUY'
    assert result['confidence'] == 0.9


def test_parse_llm_response_invalid_confidence_uses_fallback():
    text = "SIGNAL: BUY\nCONFIDENCE: not_a_number\nREASONING: Testing fallback."
    result = parse_llm_response(text, 0.65)
    assert result['confidence'] == 0.65


def test_parse_llm_response_confidence_out_of_range_uses_fallback():
    text = "SIGNAL: BUY\nCONFIDENCE: 5.0\nREASONING: Testing range."
    result = parse_llm_response(text, 0.5)
    assert result['confidence'] == 0.5


def test_build_prompt_all_analysts():
    for name in ANALYST_PROMPTS:
        prompt = build_prompt(name, "EURUSD", "1H")
        assert prompt is not None
        assert "EURUSD" in prompt
        assert "1H" in prompt
        assert "SIGNAL" in prompt
        assert "CONFIDENCE" in prompt


def test_build_prompt_unknown_analyst():
    result = build_prompt("unknown", "EURUSD", "1H")
    assert result is None


# --- LLM Client mock behavior ---

def test_llm_client_mock_returns_valid_response():
    client = LLMClient()
    # When NVIDIA NIM is configured, primary is nvidia_nim; test still validates the chain works
    response = client.analyze("Analyze EURUSD")
    assert isinstance(response, LLMResponse)
    assert response.text is not None
    assert 0.0 <= response.confidence <= 1.0


# --- All 12 Analysts with LLM ---

ALL_ANALYST_CLASSES = [
    ('market', 'apps.analysts.market', 'MarketAnalyst'),
    ('news', 'apps.analysts.news', 'NewsAnalyst'),
    ('fundamentals', 'apps.analysts.fundamentals', 'FundamentalsAnalyst'),
    ('sentiment', 'apps.analysts.sentiment', 'SentimentAnalyst'),
    ('technical', 'apps.analysts.technical', 'TechnicalAnalyst'),
    ('options', 'apps.analysts.options', 'OptionsAnalyst'),
    ('order_flow', 'apps.analysts.order_flow', 'OrderFlowAnalyst'),
    ('risk', 'apps.analysts.risk', 'RiskAnalyst'),
    ('macro', 'apps.analysts.macro', 'MacroAnalyst'),
    ('on_chain', 'apps.analysts.on_chain', 'OnChainAnalyst'),
    ('quant', 'apps.analysts.quant', 'QuantAnalyst'),
    ('compliance', 'apps.analysts.compliance', 'ComplianceAnalyst'),
]


def _import_analyst(module_path, class_name):
    import importlib
    mod = importlib.import_module(module_path)
    return getattr(mod, class_name)


@pytest.mark.asyncio
@pytest.mark.parametrize("name,module_path,class_name", ALL_ANALYST_CLASSES)
async def test_analyst_with_llm(name, module_path, class_name):
    client = LLMClient()
    analyst = _import_analyst(module_path, class_name)(llm_client=client)
    result = await analyst.analyze("EURUSD", "1H")
    assert isinstance(result, AnalystResult)
    assert result.analyst_name == name
    assert result.signal in ("BUY", "SELL", "HOLD")
    assert 0.0 <= result.confidence <= 1.0
    assert result.reasoning != ""
    assert result.data.get('data_source') == 'llm'
    assert result.data.get('llm_model') == 'mock'


@pytest.mark.asyncio
@pytest.mark.parametrize("name,module_path,class_name", ALL_ANALYST_CLASSES)
async def test_analyst_without_llm(name, module_path, class_name):
    analyst = _import_analyst(module_path, class_name)()
    assert analyst.llm_client is None
    result = await analyst.analyze("EURUSD", "1H")
    assert isinstance(result, AnalystResult)
    assert result.analyst_name == name
    assert result.signal in ("BUY", "SELL", "HOLD")
    assert 0.0 <= result.confidence <= 1.0
    assert result.reasoning != ""


@pytest.mark.parametrize("name,module_path,class_name", ALL_ANALYST_CLASSES)
def test_analyst_init_with_llm(name, module_path, class_name):
    client = LLMClient()
    analyst = _import_analyst(module_path, class_name)(llm_client=client)
    assert analyst.llm_client is client


@pytest.mark.parametrize("name,module_path,class_name", ALL_ANALYST_CLASSES)
def test_analyst_init_without_llm(name, module_path, class_name):
    analyst = _import_analyst(module_path, class_name)()
    assert analyst.llm_client is None
    assert hasattr(analyst, 'analyze')
    assert hasattr(analyst, 'get_capabilities')


@pytest.mark.parametrize("name,module_path,class_name", ALL_ANALYST_CLASSES)
def test_analyst_capabilities_preserved(name, module_path, class_name):
    client = LLMClient()
    with_llm = _import_analyst(module_path, class_name)(llm_client=client)
    without_llm = _import_analyst(module_path, class_name)()
    assert with_llm.get_capabilities() == without_llm.get_capabilities()


# --- MarketAnalyst backward compat ---

def test_market_analyst_backward_compat_with_data_manager():
    from apps.analysts.market import MarketAnalyst
    analyst = MarketAnalyst(data_manager=None)
    assert analyst.llm_client is None
    assert analyst.data_manager is None
    assert hasattr(analyst, '_calculate_rsi')


def test_market_analyst_with_both_llm_and_data_manager():
    from apps.analysts.market import MarketAnalyst
    client = LLMClient()
    analyst = MarketAnalyst(llm_client=client, data_manager=None)
    assert analyst.llm_client is client
    assert analyst.data_manager is None
