import pytest
from apps.llm.client import LLMClient
from apps.debate.agents import BullResearcher, BearResearcher
from apps.debate.engine import DebateEngine, DebateResult
from apps.debate.manager import ResearchManager, InvestmentPlan


@pytest.mark.asyncio
async def test_bull_researcher_default():
    bull = BullResearcher()
    argument = await bull.argue("EURUSD", context={})
    assert argument.stance == "BULL"
    assert argument.confidence == 0.6
    assert "EURUSD" in argument.reasoning


@pytest.mark.asyncio
async def test_bear_researcher_default():
    bear = BearResearcher()
    argument = await bear.argue("EURUSD", context={})
    assert argument.stance == "BEAR"
    assert argument.confidence == 0.6
    assert "EURUSD" in argument.reasoning


@pytest.mark.asyncio
async def test_bull_researcher_with_llm():
    bull = BullResearcher(llm_client=LLMClient())
    argument = await bull.argue("EURUSD", context={})
    assert argument.stance == "BULL"
    assert argument.confidence > 0


@pytest.mark.asyncio
async def test_bear_researcher_with_llm():
    bear = BearResearcher(llm_client=LLMClient())
    argument = await bear.argue("EURUSD", context={})
    assert argument.stance == "BEAR"
    assert argument.confidence > 0


@pytest.mark.asyncio
async def test_debate_rounds():
    engine = DebateEngine(max_rounds=2)
    result = await engine.debate("EURUSD")
    assert result.rounds == 2
    assert len(result.arguments) == 4
    assert result.winner in ("BULL", "BEAR", "NEUTRAL")


@pytest.mark.asyncio
async def test_debate_single_round():
    engine = DebateEngine(max_rounds=1)
    result = await engine.debate("EURUSD")
    assert result.rounds == 1
    assert len(result.arguments) == 2
    assert result.bull_confidence > 0
    assert result.bear_confidence > 0


@pytest.mark.asyncio
async def test_debate_with_context():
    engine = DebateEngine(max_rounds=2)
    context = {"price": 1.1050, "trend": "up"}
    result = await engine.debate("EURUSD", context=context)
    assert result.rounds == 2
    # Context should have been augmented with round arguments
    assert "round_0_bull" in context
    assert "round_0_bear" in context


@pytest.mark.asyncio
async def test_research_manager_default():
    manager = ResearchManager()
    engine = DebateEngine(max_rounds=1)
    debate_result = await engine.debate("EURUSD")
    plan = await manager.evaluate(debate_result)
    assert plan.action in ("BUY", "SELL", "HOLD")
    assert plan.confidence > 0
    assert plan.debate_winner == debate_result.winner


@pytest.mark.asyncio
async def test_research_manager_with_llm():
    manager = ResearchManager(llm_client=LLMClient())
    engine = DebateEngine(max_rounds=1)
    debate_result = await engine.debate("EURUSD")
    plan = await manager.evaluate(debate_result)
    assert plan.action in ("BUY", "SELL", "HOLD")
    assert plan.confidence > 0


@pytest.mark.asyncio
async def test_investment_plan_bull_winner():
    manager = ResearchManager()
    from apps.debate.agents import Argument

    dr = DebateResult(
        rounds=1,
        winner="BULL",
        arguments=[],
        bull_confidence=0.8,
        bear_confidence=0.5,
    )
    plan = await manager.evaluate(dr)
    assert plan.action == "BUY"
    assert plan.debate_winner == "BULL"


@pytest.mark.asyncio
async def test_investment_plan_bear_winner():
    manager = ResearchManager()
    from apps.debate.agents import Argument

    dr = DebateResult(
        rounds=1,
        winner="BEAR",
        arguments=[],
        bull_confidence=0.5,
        bear_confidence=0.8,
    )
    plan = await manager.evaluate(dr)
    assert plan.action == "SELL"
    assert plan.debate_winner == "BEAR"


@pytest.mark.asyncio
async def test_investment_plan_neutral():
    manager = ResearchManager()
    from apps.debate.agents import Argument

    dr = DebateResult(
        rounds=1,
        winner="NEUTRAL",
        arguments=[],
        bull_confidence=0.6,
        bear_confidence=0.6,
    )
    plan = await manager.evaluate(dr)
    assert plan.action == "HOLD"
    assert plan.debate_winner == "NEUTRAL"


@pytest.mark.asyncio
async def test_full_debate_pipeline():
    """End-to-end: debate -> evaluate -> plan."""
    engine = DebateEngine(max_rounds=1)
    debate_result = await engine.debate("EURUSD")

    manager = ResearchManager()
    plan = await manager.evaluate(debate_result)

    assert plan.action in ("BUY", "SELL", "HOLD")
    assert plan.confidence > 0
    assert plan.debate_winner == debate_result.winner
    assert len(plan.plan_details) > 0
