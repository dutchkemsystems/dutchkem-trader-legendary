import pytest
import asyncio
from apps.consensus.engine import ConsensusEngine
from apps.analysts.base import AnalystResult


def test_consensus_engine_creation():
    engine = ConsensusEngine()
    assert hasattr(engine, 'evaluate')


def test_vote_counting():
    from apps.consensus.voting import VoteCounter
    counter = VoteCounter()
    results = [
        AnalystResult('market', 'EURUSD', '1H', 'BUY', 0.8, 'test', {}),
        AnalystResult('news', 'EURUSD', '1H', 'BUY', 0.7, 'test', {}),
        AnalystResult('sentiment', 'EURUSD', '1H', 'SELL', 0.6, 'test', {}),
    ]
    votes = counter.count_votes(results)
    assert votes['agreement'] > 0.5
    assert votes['action'] == 'BUY'


def test_consensus_requires_70_percent():
    from apps.consensus.engine import ConsensusEngine
    from apps.analysts.market import MarketAnalyst
    from apps.analysts.news import NewsAnalyst
    from apps.analysts.sentiment import SentimentAnalyst
    engine = ConsensusEngine(analysts=[MarketAnalyst(), NewsAnalyst(), SentimentAnalyst()])
    result = asyncio.run(engine.evaluate('EURUSD', '1H'))
    assert 'action' in result
    assert 'agreement_pct' in result


def test_vote_counter_empty():
    from apps.consensus.voting import VoteCounter
    counter = VoteCounter()
    votes = counter.count_votes([])
    assert votes['action'] == 'HOLD'
    assert votes['confidence'] == 0.0
    assert votes['agreement'] == 0.0
    assert votes['votes'] == {}


def test_vote_counter_all_hold():
    from apps.consensus.voting import VoteCounter
    counter = VoteCounter()
    results = [
        AnalystResult('a', 'EURUSD', '1H', 'HOLD', 0.5, 'test', {}),
        AnalystResult('b', 'EURUSD', '1H', 'HOLD', 0.5, 'test', {}),
        AnalystResult('c', 'EURUSD', '1H', 'HOLD', 0.5, 'test', {}),
    ]
    votes = counter.count_votes(results)
    assert votes['action'] == 'HOLD'
    assert votes['agreement'] == 1.0


def test_vote_counter_tie():
    from apps.consensus.voting import VoteCounter
    counter = VoteCounter()
    results = [
        AnalystResult('a', 'EURUSD', '1H', 'BUY', 0.8, 'test', {}),
        AnalystResult('b', 'EURUSD', '1H', 'SELL', 0.8, 'test', {}),
    ]
    votes = counter.count_votes(results)
    assert votes['action'] == 'HOLD'


def test_consensus_engine_add_remove():
    engine = ConsensusEngine()
    from apps.analysts.market import MarketAnalyst
    engine.add_analyst(MarketAnalyst())
    assert len(engine.analysts) == 1
    engine.remove_analyst('market')
    assert len(engine.analysts) == 0


def test_consensus_engine_insufficient_agreement():
    from apps.consensus.voting import VoteCounter
    counter = VoteCounter()
    results = [
        AnalystResult('a', 'EURUSD', '1H', 'BUY', 0.8, 'test', {}),
        AnalystResult('b', 'EURUSD', '1H', 'SELL', 0.8, 'test', {}),
        AnalystResult('c', 'EURUSD', '1H', 'HOLD', 0.5, 'test', {}),
    ]
    votes = counter.count_votes(results)
    assert votes['agreement'] < 0.70
