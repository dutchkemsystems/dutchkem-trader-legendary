from dataclasses import dataclass
from typing import Optional
from .engine import DebateResult


@dataclass
class InvestmentPlan:
    action: str  # "BUY", "SELL", "HOLD"
    confidence: float
    reasoning: str
    debate_winner: str
    plan_details: str


class ResearchManager:
    def __init__(self, llm_client=None):
        self.llm_client = llm_client

    async def evaluate(self, debate_result: DebateResult) -> InvestmentPlan:
        if self.llm_client:
            prompt = (
                f"Evaluate debate. Winner: {debate_result.winner}. "
                f"Bull conf: {debate_result.bull_confidence}. "
                f"Bear conf: {debate_result.bear_confidence}. "
                f"Produce investment plan."
            )
            response = self.llm_client.analyze(prompt)
            action = (
                "BUY"
                if debate_result.winner == "BULL"
                else "SELL"
                if debate_result.winner == "BEAR"
                else "HOLD"
            )
            return InvestmentPlan(
                action=action,
                confidence=response.confidence,
                reasoning=response.text,
                debate_winner=debate_result.winner,
                plan_details=response.text,
            )

        action = (
            "BUY"
            if debate_result.winner == "BULL"
            else "SELL"
            if debate_result.winner == "BEAR"
            else "HOLD"
        )
        conf = (
            debate_result.bull_confidence
            if action == "BUY"
            else debate_result.bear_confidence
            if action == "SELL"
            else 0.5
        )
        return InvestmentPlan(
            action=action,
            confidence=conf,
            reasoning=f"Based on debate winner: {debate_result.winner}",
            debate_winner=debate_result.winner,
            plan_details=f"Recommended {action} based on {debate_result.winner} argument",
        )
