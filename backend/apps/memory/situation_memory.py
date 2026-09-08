import uuid
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime, timezone
from .bm25_retriever import BM25Retriever


@dataclass
class Situation:
    id: str
    symbol: str
    situation: str
    outcome: str
    lesson: str
    timestamp: datetime
    relevance_score: float = 0.0


class FinancialSituationMemory:
    def __init__(self):
        self.situations: List[Situation] = []
        self.retriever = BM25Retriever()

    def store(self, symbol: str, situation: str, outcome: str, lesson: str):
        s = Situation(
            id=str(uuid.uuid4()),
            symbol=symbol,
            situation=situation,
            outcome=outcome,
            lesson=lesson,
            timestamp=datetime.now(timezone.utc),
        )
        self.situations.append(s)
        self.retriever.add_documents([f"{situation} {lesson}"])

    def retrieve(self, query: str, top_k: int = 3) -> List[Situation]:
        results = self.retriever.search(query, top_k)
        retrieved = []
        for idx, score in results:
            if idx < len(self.situations):
                s = self.situations[idx]
                s.relevance_score = float(score)
                retrieved.append(s)
        return retrieved

    def count(self) -> int:
        return len(self.situations)
