from dataclasses import dataclass, field
from typing import Dict, Any, List


@dataclass
class Argument:
    stance: str  # "BULL" or "BEAR"
    confidence: float
    reasoning: str
    evidence: List[str] = field(default_factory=list)


class BullResearcher:
    def __init__(self, llm_client=None):
        self.llm_client = llm_client

    async def argue(self, symbol: str, context: Dict[str, Any]) -> Argument:
        if self.llm_client:
            prompt = f"Bullish case for {symbol}. Context: {context}. Argue why price will rise."
            response = self.llm_client.analyze(prompt)
            return Argument(
                stance="BULL",
                confidence=response.confidence,
                reasoning=response.text,
                evidence=[],
            )
        return Argument(
            stance="BULL",
            confidence=0.6,
            reasoning=f"Default bullish argument for {symbol}",
            evidence=[],
        )


class BearResearcher:
    def __init__(self, llm_client=None):
        self.llm_client = llm_client

    async def argue(self, symbol: str, context: Dict[str, Any]) -> Argument:
        if self.llm_client:
            prompt = f"Bearish case for {symbol}. Context: {context}. Argue why price will fall."
            response = self.llm_client.analyze(prompt)
            return Argument(
                stance="BEAR",
                confidence=response.confidence,
                reasoning=response.text,
                evidence=[],
            )
        return Argument(
            stance="BEAR",
            confidence=0.6,
            reasoning=f"Default bearish argument for {symbol}",
            evidence=[],
        )
