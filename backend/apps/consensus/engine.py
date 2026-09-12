import asyncio
import logging
from typing import List, Dict, Any, Optional
from apps.analysts.base import BaseAnalyst, AnalystResult
from apps.consensus.voting import VoteCounter

logger = logging.getLogger(__name__)


class ConsensusEngine:
    def __init__(
        self,
        analysts: List[BaseAnalyst] = None,
        ml_predictor=None,
        debate_engine=None,
        memory=None,
    ):
        self.analysts = analysts or []
        self.ml_predictor = ml_predictor
        self.debate_engine = debate_engine
        self.memory = memory
        self.vote_counter = VoteCounter()
        self.min_agreement = 0.70

    async def evaluate(
        self,
        symbol: str,
        timeframe: str,
        use_debate: bool = False,
        use_memory: bool = False,
    ) -> Dict[str, Any]:
        # 1. Run all analysts in parallel
        tasks = [analyst.analyze(symbol, timeframe) for analyst in self.analysts]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Log any exceptions
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning(f'Analyst {self.analysts[i].__class__.__name__} failed: {result}')

        # Filter out exceptions AND stub results (data_source == "none")
        valid_results = [
            r for r in results
            if isinstance(r, AnalystResult) and r.data_source != "none"
        ]

        # Log filtered stubs
        stub_count = sum(1 for r in results if isinstance(r, AnalystResult) and r.data_source == "none")
        if stub_count > 0:
            logger.info(f'Filtered {stub_count} stub analysts from consensus')

        # 2. Count votes
        votes = self.vote_counter.count_votes(valid_results)

        # Build base result
        if votes['agreement'] < self.min_agreement:
            result = {
                'action': 'HOLD',
                'confidence': votes['confidence'],
                'agreement_pct': votes['agreement'],
                'reason': f'Insufficient agreement: {votes["agreement"]:.1%} < {self.min_agreement:.1%}',
                'votes': votes['votes']
            }
        else:
            result = {
                'action': votes['action'],
                'confidence': votes['confidence'],
                'agreement_pct': votes['agreement'],
                'reason': f'Consensus reached: {votes["action"]} with {votes["agreement"]:.1%} agreement',
                'votes': votes['votes']
            }

        # 3. Optional: run debate and enrich result
        if use_debate and self.debate_engine:
            try:
                debate_result = await self.debate_engine.debate(symbol)
                result['debate'] = {
                    'winner': debate_result.winner,
                    'bull_confidence': debate_result.bull_confidence,
                    'bear_confidence': debate_result.bear_confidence,
                    'rounds': debate_result.rounds,
                }
                # Boost confidence when debate aligns with consensus action
                if result['action'] != 'HOLD':
                    aligned = (
                        (result['action'] == 'BUY' and debate_result.winner == 'BULL')
                        or (result['action'] == 'SELL' and debate_result.winner == 'BEAR')
                    )
                    if aligned:
                        avg_debate_conf = (
                            debate_result.bull_confidence
                            if debate_result.winner == 'BULL'
                            else debate_result.bear_confidence
                        )
                        result['confidence'] = min(
                            1.0, result['confidence'] * 0.6 + avg_debate_conf * 0.4
                        )
            except Exception as e:
                logger.warning(f'Debate failed: {e}')
                result['debate'] = {'error': str(e)}

        # 4. Optional: enrich context with memory
        if use_memory and self.memory:
            try:
                similar = self.memory.retrieve(f"{symbol} {timeframe}")
                result['similar_situations'] = [
                    {
                        'symbol': s.symbol,
                        'situation': s.situation,
                        'outcome': s.outcome,
                        'lesson': s.lesson,
                        'relevance_score': s.relevance_score,
                    }
                    for s in similar
                ]
            except Exception as e:
                logger.warning(f'Memory retrieval failed: {e}')
                result['similar_situations'] = []

        return result

    def add_analyst(self, analyst: BaseAnalyst):
        self.analysts.append(analyst)

    def remove_analyst(self, analyst_name: str):
        original_count = len(self.analysts)
        self.analysts = [a for a in self.analysts if a.__class__.__name__.lower().replace('analyst', '') != analyst_name]
        if len(self.analysts) == original_count:
            raise ValueError(f'Analyst "{analyst_name}" not found')
