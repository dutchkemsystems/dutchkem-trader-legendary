import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
os.environ['DATABASE_URL'] = 'sqlite:///test_db.sqlite3'

import django
django.setup()

import pytest
from django.contrib.auth.models import User
from apps.analysts.market import MarketAnalyst
from apps.analysts.news import NewsAnalyst
from apps.consensus.engine import ConsensusEngine
from apps.scanner.scanner import MultiTimeframeScanner


@pytest.fixture
def market_analyst():
    return MarketAnalyst()


@pytest.fixture
def news_analyst():
    return NewsAnalyst()


@pytest.fixture
def consensus_engine():
    return ConsensusEngine(analysts=[MarketAnalyst(), NewsAnalyst()])


@pytest.fixture
def scanner():
    return MultiTimeframeScanner()


@pytest.fixture
def test_user(db):
    user = User.objects.create_user(
        username='test_trader',
        email='test@dutchkem.com',
        password='testpass123'
    )
    return user
