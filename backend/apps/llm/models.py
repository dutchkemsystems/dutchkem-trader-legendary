from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class LLMResponse:
    text: str
    confidence: float
    parsed: Dict[str, Any] = field(default_factory=dict)
    model_used: str = "mock"
    tokens_used: int = 0
