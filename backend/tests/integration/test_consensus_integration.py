import pytest
from apps.consensus.engine import ConsensusEngine
from apps.debate.engine import DebateEngine
from apps.memory.situation_memory import FinancialSituationMemory
from apps.analysts.base import AnalystResult


class StubAnalyst:
    """Deterministic analyst for testing — returns a fixed signal."""

    def __init__(self, name: str, signal: str, confidence: float = 0.8):
        self._name = name
        self._signal = signal
        self._confidence = confidence

    async def analyze(self, symbol: str, timeframe: str) -> AnalystResult:
        return AnalystResult(
            analyst_name=self._name,
            symbol=symbol,
            timeframe=timeframe,
            signal=self._signal,
            confidence=self._confidence,
            reasoning=f"Stub {self._signal}",
        )

    def get_capabilities(self):
        return []


@pytest.mark.asyncio
async def test_consensus_backward_compatible():
    engine = ConsensusEngine(
        analysts=[
            StubAnalyst("a1", "BUY", 0.9),
            StubAnalyst("a2", "BUY", 0.8),
            StubAnalyst("a3", "BUY", 0.7),
        ]
    )
    result = await engine.evaluate("EURUSD", "1H")
    assert result["action"] == "BUY"
    assert "debate" not in result
    assert "similar_situations" not in result


@pytest.mark.asyncio
async def test_consensus_with_memory_enriches_result():
    memory = FinancialSituationMemory()
    memory.store("EURUSD", "strong uptrend with breakout", "profit", "trend following works")
    memory.store("EURUSD", "consolidation before breakout", "profit", "patience pays")
    memory.store("GBPUSD", "downtrend", "loss", "don't catch falling knives")

    engine = ConsensusEngine(
        analysts=[
            StubAnalyst("a1", "BUY", 0.9),
            StubAnalyst("a2", "BUY", 0.8),
            StubAnalyst("a3", "BUY", 0.7),
        ],
        memory=memory,
    )
    result = await engine.evaluate("EURUSD", "1H", use_memory=True)

    assert result["action"] == "BUY"
    assert "similar_situations" in result
    assert len(result["similar_situations"]) > 0
    assert all("lesson" in s for s in result["similar_situations"])


@pytest.mark.asyncio
async def test_consensus_without_memory_flag_no_enrichment():
    memory = FinancialSituationMemory()
    memory.store("EURUSD", "uptrend", "profit", "works")

    engine = ConsensusEngine(
        analysts=[
            StubAnalyst("a1", "BUY", 0.9),
            StubAnalyst("a2", "BUY", 0.8),
            StubAnalyst("a3", "BUY", 0.7),
        ],
        memory=memory,
    )
    result = await engine.evaluate("EURUSD", "1H", use_memory=False)

    assert result["action"] == "BUY"
    assert "similar_situations" not in result


@pytest.mark.asyncio
async def test_consensus_with_debate_enriches_result():
    debate = DebateEngine(llm_client=None, max_rounds=1)

    engine = ConsensusEngine(
        analysts=[
            StubAnalyst("a1", "BUY", 0.9),
            StubAnalyst("a2", "BUY", 0.8),
            StubAnalyst("a3", "BUY", 0.7),
        ],
        debate_engine=debate,
    )
    result = await engine.evaluate("EURUSD", "1H", use_debate=True)

    assert result["action"] == "BUY"
    assert "debate" in result
    assert result["debate"]["winner"] in ("BULL", "BEAR", "NEUTRAL")
    assert "bull_confidence" in result["debate"]
    assert "bear_confidence" in result["debate"]


@pytest.mark.asyncio
async def test_consensus_without_debate_flag_no_enrichment():
    debate = DebateEngine(llm_client=None, max_rounds=1)

    engine = ConsensusEngine(
        analysts=[
            StubAnalyst("a1", "BUY", 0.9),
            StubAnalyst("a2", "BUY", 0.8),
            StubAnalyst("a3", "BUY", 0.7),
        ],
        debate_engine=debate,
    )
    result = await engine.evaluate("EURUSD", "1H", use_debate=False)

    assert result["action"] == "BUY"
    assert "debate" not in result


@pytest.mark.asyncio
async def test_consensus_with_both_debate_and_memory():
    memory = FinancialSituationMemory()
    memory.store("EURUSD", "bullish breakout", "profit", "momentum works")

    debate = DebateEngine(llm_client=None, max_rounds=1)

    engine = ConsensusEngine(
        analysts=[
            StubAnalyst("a1", "BUY", 0.9),
            StubAnalyst("a2", "BUY", 0.8),
            StubAnalyst("a3", "BUY", 0.7),
        ],
        debate_engine=debate,
        memory=memory,
    )
    result = await engine.evaluate("EURUSD", "1H", use_debate=True, use_memory=True)

    assert result["action"] == "BUY"
    assert "debate" in result
    assert "similar_situations" in result


@pytest.mark.asyncio
async def test_consensus_debate_boosts_confidence_when_aligned():
    debate = DebateEngine(llm_client=None, max_rounds=1)
    # Default debate (no LLM) produces BULL with 0.6 confidence — aligned with BUY consensus

    engine = ConsensusEngine(
        analysts=[
            StubAnalyst("a1", "BUY", 0.7),
            StubAnalyst("a2", "BUY", 0.65),
            StubAnalyst("a3", "BUY", 0.6),
        ],
        debate_engine=debate,
    )
    result_with = await engine.evaluate("EURUSD", "1H", use_debate=True)
    result_without = await engine.evaluate("EURUSD", "1H", use_debate=False)

    # Debate alignment should not reduce confidence
    assert result_with["confidence"] >= result_without["confidence"]
