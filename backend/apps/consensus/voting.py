from typing import List, Dict
from apps.analysts.base import AnalystResult


class VoteCounter:
    def count_votes(self, results: List[AnalystResult]) -> Dict:
        if not results:
            return {'action': 'HOLD', 'confidence': 0.0, 'agreement': 0.0, 'votes': {}}

        buy_votes = sum(1 for r in results if r.signal == 'BUY')
        sell_votes = sum(1 for r in results if r.signal == 'SELL')
        hold_votes = sum(1 for r in results if r.signal == 'HOLD')
        total = len(results)

        if buy_votes > sell_votes and buy_votes > hold_votes:
            action = 'BUY'
            agreement = buy_votes / total
            confidence = sum(r.confidence for r in results if r.signal == 'BUY') / buy_votes
        elif sell_votes > buy_votes and sell_votes > hold_votes:
            action = 'SELL'
            agreement = sell_votes / total
            confidence = sum(r.confidence for r in results if r.signal == 'SELL') / sell_votes
        else:
            action = 'HOLD'
            agreement = hold_votes / total if hold_votes > 0 else 0.0
            confidence = 0.5

        votes = {r.analyst_name: r.signal for r in results}

        return {
            'action': action,
            'confidence': confidence,
            'agreement': agreement,
            'votes': votes
        }
