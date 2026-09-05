import asyncio
import logging
from typing import List, Dict, Any
from apps.analysts.base import BaseAnalyst, AnalystResult
from apps.consensus.voting import VoteCounter

logger = logging.getLogger(__name__)


class ConsensusEngine:
    def __init__(self, analysts: List[BaseAnalyst] = None):
        self.analysts = analysts or []
        self.vote_counter = VoteCounter()
        self.min_agreement = 0.70

    async def evaluate(self, symbol: str, timeframe: str) -> Dict[str, Any]:
        # 1. Run all analysts in parallel
        tasks = [analyst.analyze(symbol, timeframe) for analyst in self.analysts]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Log any exceptions
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning(f'Analyst {self.analysts[i].__class__.__name__} failed: {result}')

        # Filter out exceptions
        valid_results = [r for r in results if isinstance(r, AnalystResult)]

        # 2. Count votes
        votes = self.vote_counter.count_votes(valid_results)

        # 3. Check agreement threshold
        if votes['agreement'] < self.min_agreement:
            return {
                'action': 'HOLD',
                'confidence': votes['confidence'],
                'agreement_pct': votes['agreement'],
                'reason': f'Insufficient agreement: {votes["agreement"]:.1%} < {self.min_agreement:.1%}',
                'votes': votes['votes']
            }

        return {
            'action': votes['action'],
            'confidence': votes['confidence'],
            'agreement_pct': votes['agreement'],
            'reason': f'Consensus reached: {votes["action"]} with {votes["agreement"]:.1%} agreement',
            'votes': votes['votes']
        }

    def add_analyst(self, analyst: BaseAnalyst):
        self.analysts.append(analyst)

    def remove_analyst(self, analyst_name: str):
        original_count = len(self.analysts)
        self.analysts = [a for a in self.analysts if a.__class__.__name__.lower().replace('analyst', '') != analyst_name]
        if len(self.analysts) == original_count:
            raise ValueError(f'Analyst "{analyst_name}" not found')
