from dataclasses import dataclass, field
from typing import Dict, Any, List
from .agents import BullResearcher, BearResearcher, Argument


@dataclass
class DebateResult:
    rounds: int
    winner: str  # "BULL", "BEAR", "NEUTRAL"
    arguments: List[Argument]
    bull_confidence: float
    bear_confidence: float


class DebateEngine:
    def __init__(self, llm_client=None, max_rounds: int = 3):
        self.bull = BullResearcher(llm_client)
        self.bear = BearResearcher(llm_client)
        self.max_rounds = max_rounds

    async def debate(self, symbol: str, context: Dict[str, Any] = None) -> DebateResult:
        context = context or {}
        arguments: List[Argument] = []

        for round_num in range(self.max_rounds):
            bull_arg = await self.bull.argue(symbol, context)
            bear_arg = await self.bear.argue(symbol, context)
            arguments.extend([bull_arg, bear_arg])

            # Update context with arguments for next round
            context[f"round_{round_num}_bull"] = bull_arg.reasoning
            context[f"round_{round_num}_bear"] = bear_arg.reasoning

        bull_args = [a for a in arguments if a.stance == "BULL"]
        bear_args = [a for a in arguments if a.stance == "BEAR"]

        bull_conf = (
            sum(a.confidence for a in bull_args) / len(bull_args) if bull_args else 0.0
        )
        bear_conf = (
            sum(a.confidence for a in bear_args) / len(bear_args) if bear_args else 0.0
        )

        if bull_conf > bear_conf + 0.1:
            winner = "BULL"
        elif bear_conf > bull_conf + 0.1:
            winner = "BEAR"
        else:
            winner = "NEUTRAL"

        return DebateResult(
            rounds=self.max_rounds,
            winner=winner,
            arguments=arguments,
            bull_confidence=bull_conf,
            bear_confidence=bear_conf,
        )
