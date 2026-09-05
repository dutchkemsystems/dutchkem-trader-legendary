import pytest
from django.contrib.auth.models import User
from django_app.models import AnalystResult, ConsensusResult, Trade


@pytest.mark.django_db
def test_analyst_result_creation(test_user):
    result = AnalystResult.objects.create(
        user=test_user,
        analyst_type='market',
        ticker='EURUSD',
        signal='BUY',
        confidence=0.85,
        reasoning='Strong signal',
        metadata_json={'rsi': 65}
    )
    assert result.id is not None
    assert result.analyst_type == 'market'
    assert result.ticker == 'EURUSD'
    assert result.signal == 'BUY'
    assert result.confidence == 0.85
    assert result.metadata_json == {'rsi': 65}


@pytest.mark.django_db
def test_consensus_result_creation(test_user):
    market_result = AnalystResult.objects.create(
        user=test_user,
        analyst_type='market',
        ticker='EURUSD',
        signal='BUY',
        confidence=0.85,
        reasoning='Market says buy'
    )
    news_result = AnalystResult.objects.create(
        user=test_user,
        analyst_type='news',
        ticker='EURUSD',
        signal='BUY',
        confidence=0.75,
        reasoning='News sentiment positive'
    )

    result = ConsensusResult.objects.create(
        user=test_user,
        ticker='EURUSD',
        consensus_signal='BUY',
        weight=0.80,
        reasoning='Strong consensus'
    )
    result.analyst_results.add(market_result, news_result)

    assert result.id is not None
    assert result.consensus_signal == 'BUY'
    assert result.weight == 0.80
    assert result.analyst_results.count() == 2


@pytest.mark.django_db
def test_trade_creation(test_user):
    trade = Trade.objects.create(
        user=test_user,
        ticker='EURUSD',
        side='BUY',
        quantity=0.40,
        price=1.0890,
        status='PENDING'
    )
    assert trade.id is not None
    assert trade.status == 'PENDING'
    assert trade.side == 'BUY'
    assert trade.ticker == 'EURUSD'
    assert float(trade.quantity) == 0.40
    assert float(trade.price) == 1.0890


@pytest.mark.django_db
def test_analyst_result_str(test_user):
    result = AnalystResult.objects.create(
        user=test_user,
        analyst_type='market',
        ticker='EURUSD',
        signal='BUY',
        confidence=85,
        reasoning='Strong signal'
    )
    assert 'market' in str(result)
    assert 'EURUSD' in str(result)


@pytest.mark.django_db
def test_trade_status_choices():
    assert Trade.Status.PENDING == 'PENDING'
    assert Trade.Status.EXECUTED == 'EXECUTED'
    assert Trade.Status.CANCELLED == 'CANCELLED'
    assert Trade.Status.FAILED == 'FAILED'


@pytest.mark.django_db
def test_trade_side_choices():
    assert Trade.Side.BUY == 'BUY'
    assert Trade.Side.SELL == 'SELL'


@pytest.mark.django_db
def test_consensus_result_str(test_user):
    result = ConsensusResult.objects.create(
        user=test_user,
        ticker='EURUSD',
        consensus_signal='BUY',
        weight=0.80,
        reasoning='Strong consensus'
    )
    assert 'EURUSD' in str(result)
    assert 'BUY' in str(result)
