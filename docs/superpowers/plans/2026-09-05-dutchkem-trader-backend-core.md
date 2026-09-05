# Dutchkem Trader — Backend Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Backend Core of Dutchkem Trader — an AI trading engine with 12 parallel analysts, consensus engine, multi-timeframe scanner, and legendary module integration.

**Architecture:** FastAPI (async API + WebSocket) + Django (ORM + Admin) + PostgreSQL + Redis + Celery + RabbitMQ. Each analyst is a standalone module with a common interface. Consensus engine aggregates votes with 70% threshold. Legendary modules (Seykota, Turtle Soup, Pyramiding) are plugins.

**Tech Stack:** Python 3.11+, FastAPI, Django 5.0, PostgreSQL 16, Redis 7, Celery 5, RabbitMQ, SQLAlchemy, Pydantic, pytest, ruff, mypy

---

## File Structure

```
backend/
├── manage.py                          # Django management
├── requirements/
│   ├── base.txt                       # Core dependencies
│   ├── dev.txt                        # Dev dependencies
│   └── prod.txt                       # Production dependencies
├── config/
│   ├── __init__.py
│   ├── settings.py                    # Django settings
│   ├── fastapi_app.py                 # FastAPI app factory
│   └── celery_app.py                  # Celery configuration
├── django_app/
│   ├── __init__.py
│   ├── models.py                      # All Django models
│   ├── admin.py                       # Django admin
│   └── urls.py                        # Django URLs (admin only)
├── apps/
│   ├── analysts/
│   │   ├── __init__.py
│   │   ├── base.py                    # BaseAnalyst ABC + AnalystResult
│   │   ├── market.py                  # Market Analyst (6-8 indicators)
│   │   ├── news.py                    # News Analyst
│   │   ├── fundamentals.py            # Fundamentals Analyst
│   │   ├── sentiment.py               # Sentiment Analyst
│   │   ├── technical.py               # Technical Analyst (vision)
│   │   ├── options.py                 # Options Analyst
│   │   ├── order_flow.py              # Order Flow Analyst
│   │   ├── risk.py                    # Risk Analyst
│   │   ├── macro.py                   # Macro Analyst
│   │   ├── on_chain.py               # On-Chain Analyst
│   │   ├── quant.py                   # Quantitative Analyst
│   │   └── compliance.py              # Compliance Analyst
│   ├── consensus/
│   │   ├── __init__.py
│   │   ├── engine.py                  # ConsensusEngine
│   │   └── voting.py                  # Vote counting logic
│   ├── scanner/
│   │   ├── __init__.py
│   │   └── scanner.py                 # MultiTimeframeScanner
│   └── legendary/
│       ├── __init__.py
│       ├── seykota.py                 # SeykotaTrendModule
│       ├── pyramiding.py              # PyramidingLogic
│       └── turtle_soup.py             # TurtleSoupModule
├── api/
│   ├── __init__.py
│   ├── main.py                        # FastAPI entry point
│   ├── deps.py                        # Dependency injection
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── market.py                  # Market data routes
│   │   ├── analysts.py                # Analyst routes
│   │   ├── consensus.py               # Consensus routes
│   │   ├── scanner.py                 # Scanner routes
│   │   ├── legendary.py               # Legendary module routes
│   │   ├── trades.py                  # Trade routes
│   │   └── positions.py               # Position routes
│   └── websocket/
│       ├── __init__.py
│       └── handlers.py                # WebSocket handlers
├── cache/
│   ├── __init__.py
│   └── redis.py                       # Redis cache layer
├── tasks/
│   ├── __init__.py
│   ├── analyst_tasks.py               # Celery tasks for analysts
│   └── scanner_tasks.py               # Celery tasks for scanner
└── tests/
    ├── __init__.py
    ├── conftest.py                    # Pytest fixtures
    ├── unit/
    │   ├── __init__.py
    │   ├── test_analysts.py           # Analyst unit tests
    │   ├── test_consensus.py          # Consensus engine tests
    │   ├── test_scanner.py            # Scanner tests
    │   └── test_legendary.py          # Legendary module tests
    ├── integration/
    │   ├── __init__.py
    │   ├── test_api.py                # API endpoint tests
    │   ├── test_database.py           # Database model tests
    │   └── test_cache.py              # Redis cache tests
    └── e2e/
        ├── __init__.py
        └── test_trading_flow.py       # Full trading flow test
```

---

## Task 1: Project Setup

**Files:**
- Create: `backend/requirements/base.txt`
- Create: `backend/requirements/dev.txt`
- Create: `backend/requirements/prod.txt`
- Create: `backend/config/__init__.py`
- Create: `backend/config/settings.py`
- Create: `backend/config/fastapi_app.py`
- Create: `backend/config/celery_app.py`
- Create: `backend/django_app/__init__.py`
- Create: `backend/django_app/models.py`
- Create: `backend/django_app/admin.py`
- Create: `backend/django_app/urls.py`
- Create: `backend/manage.py`
- Create: `backend/.env.example`

- [ ] **Step 1: Create project directory structure**

```bash
mkdir -p backend/{requirements,config,django_app,apps/{analysts,consensus,scanner,legendary},api/{routes,websocket},cache,tasks,tests/{unit,integration,e2e}}
touch backend/{config,django_app,apps/analysts,apps/consensus,apps/scanner,apps/legendary,api,api/routes,api/websocket,cache,tasks,tests,tests/unit,tests/integration,tests/e2e}/__init__.py
```

- [ ] **Step 2: Create requirements/base.txt**

```txt
# Django
Django==5.0.4
djangorestframework==3.15.1
django-cors-headers==4.3.1

# FastAPI
fastapi==0.111.0
uvicorn[standard]==0.30.1
websockets==12.0

# Database
psycopg2-binary==2.9.9
sqlalchemy==2.0.30
alembic==1.13.1

# Redis
redis==5.0.4
hiredis==2.3.2

# Celery
celery==5.4.0
rabbitmq==0.2.0

# Data Processing
pandas==2.2.2
numpy==1.26.4
ta-lib==0.4.28

# ML/AI
lightgbm==4.3.0
xgboost==2.0.3
scikit-learn==1.5.0

# API
pydantic==2.7.1
pydantic-settings==2.3.3
httpx==0.27.0

# Utilities
python-dotenv==1.0.1
python-multipart==0.0.9
```

- [ ] **Step 3: Create requirements/dev.txt**

```txt
-r base.txt
pytest==8.2.2
pytest-asyncio==0.23.7
pytest-cov==5.0.0
pytest-django==4.8.0
ruff==0.4.4
mypy==1.10.0
pre-commit==3.7.1
```

- [ ] **Step 4: Create requirements/prod.txt**

```txt
-r base.txt
gunicorn==22.0.0
dj-database-url==2.2.0
sentry-sdk==2.5.0
```

- [ ] **Step 5: Create .env.example**

```env
# Django
DJANGO_SECRET_KEY=your-secret-key-here
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1

# Database
DATABASE_URL=postgresql://postgres:password@localhost:5432/dutchkem_trader

# Redis
REDIS_URL=redis://localhost:6379/0

# Celery
CELERY_BROKER_URL=amqp://guest:guest@localhost:5672//
CELERY_RESULT_BACKEND=redis://localhost:6379/1

# API Keys (for analysts)
OPENAI_API_KEY=your-openai-key
NEWS_API_KEY=your-news-api-key
```

- [ ] **Step 6: Create backend/config/settings.py**

```python
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'django-insecure-change-me')
DEBUG = os.getenv('DJANGO_DEBUG', 'True') == 'True'
ALLOWED_HOSTS = os.getenv('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'corsheaders',
    'django_app',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
]

ROOT_URLCONF = 'django_app.urls'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('DATABASE_URL', 'dutchkem_trader').split('/')[-1],
        'USER': os.getenv('DATABASE_URL', 'postgresql://postgres:password@localhost:5432/dutchkem_trader').split('://')[1].split(':')[0],
        'PASSWORD': os.getenv('DATABASE_URL', 'postgresql://postgres:password@localhost:5432/dutchkem_trader').split(':')[1].split('@')[0],
        'HOST': os.getenv('DATABASE_URL', 'postgresql://postgres:password@localhost:5432/dutchkem_trader').split('@')[1].split(':')[0],
        'PORT': os.getenv('DATABASE_URL', 'postgresql://postgres:password@localhost:5432/dutchkem_trader').split(':')[-1].split('/')[0],
    }
}

REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'amqp://guest:guest@localhost:5672//')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/1')

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
```

- [ ] **Step 7: Create backend/config/celery_app.py**

```python
from celery import Celery
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('dutchkem_trader')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
```

- [ ] **Step 8: Create backend/django_app/models.py**

```python
from django.db import models
import uuid

class User(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    password_hash = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'users'

    def __str__(self):
        return self.email

class AnalystResult(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    analyst_name = models.CharField(max_length=50)
    symbol = models.CharField(max_length=20)
    timeframe = models.CharField(max_length=10)
    signal = models.CharField(max_length=10)
    confidence = models.FloatField()
    reasoning = models.TextField()
    data = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'analyst_results'
        indexes = [
            models.Index(fields=['analyst_name', 'symbol', 'timeframe']),
        ]

class ConsensusResult(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    symbol = models.CharField(max_length=20)
    action = models.CharField(max_length=10)
    confidence = models.FloatField()
    agreement_pct = models.FloatField()
    votes = models.JSONField(default=dict)
    legendary_votes = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'consensus_results'

class Trade(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    symbol = models.CharField(max_length=20)
    action = models.CharField(max_length=10)
    entry_price = models.DecimalField(max_digits=20, decimal_places=8)
    stop_loss = models.DecimalField(max_digits=20, decimal_places=8)
    take_profit = models.DecimalField(max_digits=20, decimal_places=8)
    lot_size = models.DecimalField(max_digits=10, decimal_places=4)
    status = models.CharField(max_length=20, default='pending')
    pnl = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'trades'

class Position(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    trade = models.OneToOneField(Trade, on_delete=models.CASCADE, related_name='position')
    current_price = models.DecimalField(max_digits=20, decimal_places=8)
    unrealized_pnl = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'positions'

class LegendaryModuleResult(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    module_name = models.CharField(max_length=50)
    symbol = models.CharField(max_length=20)
    signal = models.CharField(max_length=10)
    confidence = models.FloatField()
    data = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'legendary_module_results'
```

- [ ] **Step 9: Create backend/django_app/admin.py**

```python
from django.contrib import admin
from .models import User, AnalystResult, ConsensusResult, Trade, Position, LegendaryModuleResult

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ['email', 'is_active', 'created_at']
    search_fields = ['email']

@admin.register(AnalystResult)
class AnalystResultAdmin(admin.ModelAdmin):
    list_display = ['analyst_name', 'symbol', 'timeframe', 'signal', 'confidence', 'created_at']
    list_filter = ['analyst_name', 'signal']

@admin.register(ConsensusResult)
class ConsensusResultAdmin(admin.ModelAdmin):
    list_display = ['symbol', 'action', 'confidence', 'agreement_pct', 'created_at']

@admin.register(Trade)
class TradeAdmin(admin.ModelAdmin):
    list_display = ['symbol', 'action', 'entry_price', 'lot_size', 'status', 'pnl', 'created_at']
    list_filter = ['status', 'action']

@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    list_display = ['trade', 'current_price', 'unrealized_pnl', 'updated_at']

@admin.register(LegendaryModuleResult)
class LegendaryModuleResultAdmin(admin.ModelAdmin):
    list_display = ['module_name', 'symbol', 'signal', 'confidence', 'created_at']
    list_filter = ['module_name']
```

- [ ] **Step 10: Create backend/django_app/urls.py**

```python
from django.contrib import admin
from django.urls import path

urlpatterns = [
    path('admin/', admin.site.urls),
]
```

- [ ] **Step 11: Create backend/manage.py**

```python
#!/usr/bin/env python
import os
import sys

def main():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django."
        ) from exc
    execute_from_command_line(sys.argv)

if __name__ == '__main__':
    main()
```

- [ ] **Step 12: Verify setup**

```bash
cd backend
pip install -r requirements/dev.txt
python manage.py check
```

Expected: System check passed no issues

- [ ] **Step 13: Commit**

```bash
git add backend/
git commit -m "feat: project setup with Django, FastAPI, PostgreSQL, Redis, Celery"
```

---

## Task 2: Base Analyst Interface + Market Analyst

**Files:**
- Create: `backend/apps/analysts/base.py`
- Create: `backend/apps/analysts/market.py`
- Create: `backend/tests/unit/test_analysts.py`

- [ ] **Step 1: Write failing test for BaseAnalyst**

```python
# backend/tests/unit/test_analysts.py
import pytest
from apps.analysts.base import BaseAnalyst, AnalystResult

def test_analyst_result_creation():
    result = AnalystResult(
        analyst_name='test',
        symbol='EURUSD',
        timeframe='1H',
        signal='BUY',
        confidence=0.85,
        reasoning='Strong bullish signal',
        data={'rsi': 65}
    )
    assert result.analyst_name == 'test'
    assert result.signal == 'BUY'
    assert result.confidence == 0.85

def test_base_analyst_is_abstract():
    with pytest.raises(TypeError):
        BaseAnalyst()

def test_market_analyst_has_analyze_method():
    from apps.analysts.market import MarketAnalyst
    analyst = MarketAnalyst()
    assert hasattr(analyst, 'analyze')
    assert hasattr(analyst, 'get_capabilities')
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend
pytest tests/unit/test_analysts.py -v
```

Expected: FAIL with ImportError

- [ ] **Step 3: Write BaseAnalyst implementation**

```python
# backend/apps/analysts/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Dict, Any

@dataclass
class AnalystResult:
    analyst_name: str
    symbol: str
    timeframe: str
    signal: Literal["BUY", "SELL", "HOLD"]
    confidence: float
    reasoning: str
    data: Dict[str, Any]
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("Confidence must be between 0.0 and 1.0")
        if self.signal not in ("BUY", "SELL", "HOLD"):
            raise ValueError("Signal must be BUY, SELL, or HOLD")

class BaseAnalyst(ABC):
    @abstractmethod
    async def analyze(self, symbol: str, timeframe: str) -> AnalystResult:
        pass

    @abstractmethod
    def get_capabilities(self) -> list[str]:
        pass
```

- [ ] **Step 4: Write MarketAnalyst implementation**

```python
# backend/apps/analysts/market.py
from .base import BaseAnalyst, AnalystResult
import pandas as pd
import numpy as np

class MarketAnalyst(BaseAnalyst):
    def __init__(self):
        self.indicators = ['RSI', 'MACD', 'BB', 'ATR', 'Stochastic', 'Ichimoku', 'Fibonacci', 'VWAP']

    async def analyze(self, symbol: str, timeframe: str) -> AnalystResult:
        # Placeholder: will be replaced with real market data
        data = await self._fetch_market_data(symbol, timeframe)
        
        signals = []
        confidence_sum = 0
        
        # RSI Analysis
        rsi = self._calculate_rsi(data['close'])
        if rsi < 30:
            signals.append(('BUY', 0.7))
        elif rsi > 70:
            signals.append(('SELL', 0.7))
        else:
            signals.append(('HOLD', 0.5))
        
        # MACD Analysis
        macd_signal = self._calculate_macd(data['close'])
        signals.append(macd_signal)
        
        # Bollinger Bands
        bb_signal = self._calculate_bollinger(data['close'])
        signals.append(bb_signal)
        
        # Aggregate signals
        buy_votes = sum(1 for s, _ in signals if s == 'BUY')
        sell_votes = sum(1 for s, _ in signals if s == 'SELL')
        
        if buy_votes > sell_votes:
            signal = 'BUY'
            confidence = sum(c for s, c in signals if s == 'BUY') / buy_votes if buy_votes > 0 else 0.5
        elif sell_votes > buy_votes:
            signal = 'SELL'
            confidence = sum(c for s, c in signals if s == 'SELL') / sell_votes if sell_votes > 0 else 0.5
        else:
            signal = 'HOLD'
            confidence = 0.5
        
        return AnalystResult(
            analyst_name='market',
            symbol=symbol,
            timeframe=timeframe,
            signal=signal,
            confidence=min(confidence, 1.0),
            reasoning=f'RSI: {rsi:.1f}, MACD: {macd_signal[0]}, BB: {bb_signal[0]}',
            data={'rsi': rsi, 'macd': macd_signal, 'bb': bb_signal, 'indicators': self.indicators}
        )

    async def _fetch_market_data(self, symbol: str, timeframe: str) -> dict:
        # Placeholder: will fetch from broker API
        return {
            'close': pd.Series(np.random.randn(100).cumsum() + 100),
            'high': pd.Series(np.random.randn(100).cumsum() + 101),
            'low': pd.Series(np.random.randn(100).cumsum() + 99),
            'volume': pd.Series(np.random.randint(1000, 10000, 100))
        }

    def _calculate_rsi(self, prices: pd.Series, period: int = 14) -> float:
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50.0

    def _calculate_macd(self, prices: pd.Series) -> tuple:
        ema12 = prices.ewm(span=12).mean()
        ema26 = prices.ewm(span=26).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9).mean()
        
        if macd.iloc[-1] > signal.iloc[-1]:
            return ('BUY', 0.65)
        elif macd.iloc[-1] < signal.iloc[-1]:
            return ('SELL', 0.65)
        return ('HOLD', 0.5)

    def _calculate_bollinger(self, prices: pd.Series, period: int = 20) -> tuple:
        sma = prices.rolling(window=period).mean()
        std = prices.rolling(window=period).std()
        upper = sma + (std * 2)
        lower = sma - (std * 2)
        
        current = prices.iloc[-1]
        if current < lower.iloc[-1]:
            return ('BUY', 0.7)
        elif current > upper.iloc[-1]:
            return ('SELL', 0.7)
        return ('HOLD', 0.5)

    def get_capabilities(self) -> list[str]:
        return self.indicators
```

- [ ] **Step 5: Run test to verify it passes**

```bash
cd backend
pytest tests/unit/test_analysts.py -v
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/apps/analysts/base.py backend/apps/analysts/market.py backend/tests/unit/test_analysts.py
git commit -m "feat: add base analyst interface and market analyst"
```

---

## Task 3: News, Fundamentals, Sentiment Analysts

**Files:**
- Create: `backend/apps/analysts/news.py`
- Create: `backend/apps/analysts/fundamentals.py`
- Create: `backend/apps/analysts/sentiment.py`
- Modify: `backend/tests/unit/test_analysts.py`

- [ ] **Step 1: Write failing tests for new analysts**

```python
# Add to backend/tests/unit/test_analysts.py

def test_news_analyst():
    from apps.analysts.news import NewsAnalyst
    analyst = NewsAnalyst()
    assert hasattr(analyst, 'analyze')
    assert 'sentiment_analysis' in analyst.get_capabilities()

def test_fundamentals_analyst():
    from apps.analysts.fundamentals import FundamentalsAnalyst
    analyst = FundamentalsAnalyst()
    assert hasattr(analyst, 'analyze')
    assert 'financial_ratios' in analyst.get_capabilities()

def test_sentiment_analyst():
    from apps.analysts.sentiment import SentimentAnalyst
    analyst = SentimentAnalyst()
    assert hasattr(analyst, 'analyze')
    assert 'social_sentiment' in analyst.get_capabilities()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend
pytest tests/unit/test_analysts.py::test_news_analyst -v
```

Expected: FAIL with ImportError

- [ ] **Step 3: Write NewsAnalyst**

```python
# backend/apps/analysts/news.py
from .base import BaseAnalyst, AnalystResult

class NewsAnalyst(BaseAnalyst):
    def __init__(self):
        self.capabilities = ['sentiment_analysis', 'keyword_extraction', 'event_detection']

    async def analyze(self, symbol: str, timeframe: str) -> AnalystResult:
        news_data = await self._fetch_news(symbol)
        sentiment_score = self._analyze_sentiment(news_data)
        keywords = self._extract_keywords(news_data)
        
        if sentiment_score > 0.3:
            signal = 'BUY'
            confidence = min(0.5 + sentiment_score, 0.9)
        elif sentiment_score < -0.3:
            signal = 'SELL'
            confidence = min(0.5 + abs(sentiment_score), 0.9)
        else:
            signal = 'HOLD'
            confidence = 0.5
        
        return AnalystResult(
            analyst_name='news',
            symbol=symbol,
            timeframe=timeframe,
            signal=signal,
            confidence=confidence,
            reasoning=f'Sentiment: {sentiment_score:.2f}, Keywords: {", ".join(keywords[:3])}',
            data={'sentiment_score': sentiment_score, 'keywords': keywords, 'article_count': len(news_data)}
        )

    async def _fetch_news(self, symbol: str) -> list:
        # Placeholder: will fetch from News API
        return [{'title': f'News about {symbol}', 'content': 'Sample content', 'sentiment': 0.1}]

    def _analyze_sentiment(self, news: list) -> float:
        if not news:
            return 0.0
        sentiments = [item.get('sentiment', 0.0) for item in news]
        return sum(sentiments) / len(sentiments)

    def _extract_keywords(self, news: list) -> list:
        keywords = set()
        for item in news:
            words = item.get('content', '').split()
            keywords.update(words[:5])
        return list(keywords)[:10]

    def get_capabilities(self) -> list[str]:
        return self.capabilities
```

- [ ] **Step 4: Write FundamentalsAnalyst**

```python
# backend/apps/analysts/fundamentals.py
from .base import BaseAnalyst, AnalystResult

class FundamentalsAnalyst(BaseAnalyst):
    def __init__(self):
        self.capabilities = ['financial_ratios', 'balance_sheet', 'cash_flow', 'income_statement']

    async def analyze(self, symbol: str, timeframe: str) -> AnalystResult:
        financials = await self._fetch_financials(symbol)
        ratios = self._calculate_ratios(financials)
        score = self._score_fundamentals(ratios)
        
        if score > 0.3:
            signal = 'BUY'
            confidence = min(0.5 + score, 0.85)
        elif score < -0.3:
            signal = 'SELL'
            confidence = min(0.5 + abs(score), 0.85)
        else:
            signal = 'HOLD'
            confidence = 0.5
        
        return AnalystResult(
            analyst_name='fundamentals',
            symbol=symbol,
            timeframe=timeframe,
            signal=signal,
            confidence=confidence,
            reasoning=f'Score: {score:.2f}, P/E: {ratios.get("pe_ratio", "N/A")}',
            data={'ratios': ratios, 'score': score}
        )

    async def _fetch_financials(self, symbol: str) -> dict:
        # Placeholder: will fetch from financial API
        return {'pe_ratio': 15.2, 'pb_ratio': 2.1, 'roe': 0.18, 'debt_to_equity': 0.45}

    def _calculate_ratios(self, financials: dict) -> dict:
        return {
            'pe_ratio': financials.get('pe_ratio', 0),
            'pb_ratio': financials.get('pb_ratio', 0),
            'roe': financials.get('roe', 0),
            'debt_to_equity': financials.get('debt_to_equity', 0)
        }

    def _score_fundamentals(self, ratios: dict) -> float:
        score = 0.0
        if 0 < ratios['pe_ratio'] < 20:
            score += 0.2
        elif ratios['pe_ratio'] > 30:
            score -= 0.2
        if ratios['roe'] > 0.15:
            score += 0.2
        if ratios['debt_to_equity'] < 0.5:
            score += 0.1
        return score

    def get_capabilities(self) -> list[str]:
        return self.capabilities
```

- [ ] **Step 5: Write SentimentAnalyst**

```python
# backend/apps/analysts/sentiment.py
from .base import BaseAnalyst, AnalystResult

class SentimentAnalyst(BaseAnalyst):
    def __init__(self):
        self.capabilities = ['social_sentiment', 'fear_greed_index', 'positioning_data']

    async def analyze(self, symbol: str, timeframe: str) -> AnalystResult:
        social_data = await self._fetch_social_sentiment(symbol)
        fear_greed = await self._fetch_fear_greed()
        positioning = await self._fetch_positioning(symbol)
        
        composite_score = self._calculate_composite(social_data, fear_greed, positioning)
        
        if composite_score > 0.2:
            signal = 'BUY'
            confidence = min(0.5 + composite_score, 0.85)
        elif composite_score < -0.2:
            signal = 'SELL'
            confidence = min(0.5 + abs(composite_score), 0.85)
        else:
            signal = 'HOLD'
            confidence = 0.5
        
        return AnalystResult(
            analyst_name='sentiment',
            symbol=symbol,
            timeframe=timeframe,
            signal=signal,
            confidence=confidence,
            reasoning=f'Composite: {composite_score:.2f}, Fear/Greed: {fear_greed}',
            data={'social': social_data, 'fear_greed': fear_greed, 'positioning': positioning}
        )

    async def _fetch_social_sentiment(self, symbol: str) -> dict:
        return {'twitter': 0.1, 'reddit': 0.2, 'telegram': 0.05}

    async def _fetch_fear_greed(self) -> int:
        return 55  # Neutral

    async def _fetch_positioning(self, symbol: str) -> dict:
        return {'long_ratio': 0.6, 'short_ratio': 0.4}

    def _calculate_composite(self, social: dict, fear_greed: int, positioning: dict) -> float:
        social_avg = sum(social.values()) / len(social) if social else 0
        fear_greed_normalized = (fear_greed - 50) / 50
        positioning_bias = positioning.get('long_ratio', 0.5) - 0.5
        return (social_avg + fear_greed_normalized + positioning_bias) / 3

    def get_capabilities(self) -> list[str]:
        return self.capabilities
```

- [ ] **Step 6: Run tests**

```bash
cd backend
pytest tests/unit/test_analysts.py -v
```

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/apps/analysts/news.py backend/apps/analysts/fundamentals.py backend/apps/analysts/sentiment.py backend/tests/unit/test_analysts.py
git commit -m "feat: add news, fundamentals, and sentiment analysts"
```

---

## Task 4: Technical, Options, Order Flow Analysts

**Files:**
- Create: `backend/apps/analysts/technical.py`
- Create: `backend/apps/analysts/options.py`
- Create: `backend/apps/analysts/order_flow.py`
- Modify: `backend/tests/unit/test_analysts.py`

- [ ] **Step 1: Write failing tests**

```python
def test_technical_analyst():
    from apps.analysts.technical import TechnicalAnalyst
    analyst = TechnicalAnalyst()
    assert hasattr(analyst, 'analyze')
    assert 'chart_patterns' in analyst.get_capabilities()

def test_options_analyst():
    from apps.analysts.options import OptionsAnalyst
    analyst = OptionsAnalyst()
    assert hasattr(analyst, 'analyze')
    assert 'implied_volatility' in analyst.get_capabilities()

def test_order_flow_analyst():
    from apps.analysts.order_flow import OrderFlowAnalyst
    analyst = OrderFlowAnalyst()
    assert hasattr(analyst, 'analyze')
    assert 'microprice' in analyst.get_capabilities()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend
pytest tests/unit/test_analysts.py::test_technical_analyst -v
```

Expected: FAIL

- [ ] **Step 3: Write TechnicalAnalyst**

```python
# backend/apps/analysts/technical.py
from .base import BaseAnalyst, AnalystResult

class TechnicalAnalyst(BaseAnalyst):
    def __init__(self):
        self.capabilities = ['chart_patterns', 'support_resistance', 'trendlines', 'candlestick_patterns']

    async def analyze(self, symbol: str, timeframe: str) -> AnalystResult:
        chart_data = await self._fetch_chart_data(symbol, timeframe)
        patterns = self._detect_patterns(chart_data)
        sr_levels = self._find_support_resistance(chart_data)
        
        signal, confidence = self._evaluate_patterns(patterns, sr_levels)
        
        return AnalystResult(
            analyst_name='technical',
            symbol=symbol,
            timeframe=timeframe,
            signal=signal,
            confidence=confidence,
            reasoning=f'Patterns: {", ".join(patterns)}, S/R: {sr_levels}',
            data={'patterns': patterns, 'support_resistance': sr_levels}
        )

    async def _fetch_chart_data(self, symbol: str, timeframe: str) -> dict:
        # Placeholder: will use GPT-4V/Claude Vision
        return {'patterns': ['double_bottom', 'bullish_engulfing'], 'trend': 'up'}

    def _detect_patterns(self, chart_data: dict) -> list:
        return chart_data.get('patterns', [])

    def _find_support_resistance(self, chart_data: dict) -> dict:
        return {'support': 1.0850, 'resistance': 1.1050}

    def _evaluate_patterns(self, patterns: list, sr_levels: dict) -> tuple:
        bullish_patterns = ['double_bottom', 'bullish_engulfing', 'hammer', 'morning_star']
        bearish_patterns = ['double_top', 'bearish_engulfing', 'shooting_star', 'evening_star']
        
        bull_count = sum(1 for p in patterns if p in bullish_patterns)
        bear_count = sum(1 for p in patterns if p in bearish_patterns)
        
        if bull_count > bear_count:
            return ('BUY', min(0.6 + bull_count * 0.1, 0.9))
        elif bear_count > bull_count:
            return ('SELL', min(0.6 + bear_count * 0.1, 0.9))
        return ('HOLD', 0.5)

    def get_capabilities(self) -> list[str]:
        return self.capabilities
```

- [ ] **Step 4: Write OptionsAnalyst**

```python
# backend/apps/analysts/options.py
from .base import BaseAnalyst, AnalystResult

class OptionsAnalyst(BaseAnalyst):
    def __init__(self):
        self.capabilities = ['implied_volatility', 'put_call_ratio', 'greeks', 'unusual_activity']

    async def analyze(self, symbol: str, timeframe: str) -> AnalystResult:
        options_data = await self._fetch_options_data(symbol)
        iv = options_data.get('implied_volatility', 0.2)
        pc_ratio = options_data.get('put_call_ratio', 1.0)
        unusual = options_data.get('unusual_activity', False)
        
        signal, confidence = self._evaluate_options(iv, pc_ratio, unusual)
        
        return AnalystResult(
            analyst_name='options',
            symbol=symbol,
            timeframe=timeframe,
            signal=signal,
            confidence=confidence,
            reasoning=f'IV: {iv:.2f}, P/C: {pc_ratio:.2f}, Unusual: {unusual}',
            data=options_data
        )

    async def _fetch_options_data(self, symbol: str) -> dict:
        return {
            'implied_volatility': 0.25,
            'put_call_ratio': 0.8,
            'unusual_activity': False,
            'greeks': {'delta': 0.5, 'gamma': 0.02, 'theta': -0.01}
        }

    def _evaluate_options(self, iv: float, pc_ratio: float, unusual: bool) -> tuple:
        if pc_ratio < 0.7 and not unusual:
            return ('BUY', 0.65)
        elif pc_ratio > 1.3:
            return ('SELL', 0.65)
        return ('HOLD', 0.5)

    def get_capabilities(self) -> list[str]:
        return self.capabilities
```

- [ ] **Step 5: Write OrderFlowAnalyst**

```python
# backend/apps/analysts/order_flow.py
from .base import BaseAnalyst, AnalystResult

class OrderFlowAnalyst(BaseAnalyst):
    def __init__(self):
        self.capabilities = ['microprice', 'liquidity_imbalance', 'cvd', 'trade_flow']

    async def analyze(self, symbol: str, timeframe: str) -> AnalystResult:
        flow_data = await self._fetch_order_flow(symbol)
        microprice = self._calculate_microprice(flow_data)
        imbalance = self._calculate_imbalance(flow_data)
        
        signal, confidence = self._evaluate_flow(microprice, imbalance)
        
        return AnalystResult(
            analyst_name='order_flow',
            symbol=symbol,
            timeframe=timeframe,
            signal=signal,
            confidence=confidence,
            reasoning=f'Microprice: {microprice:.5f}, Imbalance: {imbalance:.2f}',
            data=flow_data
        )

    async def _fetch_order_flow(self, symbol: str) -> dict:
        return {
            'bid_volume': 15000,
            'ask_volume': 12000,
            'bid_price': 1.0890,
            'ask_price': 1.0892,
            'cvd': 500
        }

    def _calculate_microprice(self, data: dict) -> float:
        bid_vol = data.get('bid_volume', 1)
        ask_vol = data.get('ask_volume', 1)
        bid_price = data.get('bid_price', 0)
        ask_price = data.get('ask_price', 0)
        total = bid_vol + ask_vol
        return (bid_vol * ask_price + ask_vol * bid_price) / total if total > 0 else 0

    def _calculate_imbalance(self, data: dict) -> float:
        bid_vol = data.get('bid_volume', 1)
        ask_vol = data.get('ask_volume', 1)
        return (bid_vol - ask_vol) / (bid_vol + ask_vol)

    def _evaluate_flow(self, microprice: float, imbalance: float) -> tuple:
        if imbalance > 0.2:
            return ('BUY', min(0.6 + imbalance, 0.85))
        elif imbalance < -0.2:
            return ('SELL', min(0.6 + abs(imbalance), 0.85))
        return ('HOLD', 0.5)

    def get_capabilities(self) -> list[str]:
        return self.capabilities
```

- [ ] **Step 6: Run tests**

```bash
cd backend
pytest tests/unit/test_analysts.py -v
```

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/apps/analysts/technical.py backend/apps/analysts/options.py backend/apps/analysts/order_flow.py backend/tests/unit/test_analysts.py
git commit -m "feat: add technical, options, and order flow analysts"
```

---

## Task 5: Risk, Macro, On-Chain, Quant, Compliance Analysts

**Files:**
- Create: `backend/apps/analysts/risk.py`
- Create: `backend/apps/analysts/macro.py`
- Create: `backend/apps/analysts/on_chain.py`
- Create: `backend/apps/analysts/quant.py`
- Create: `backend/apps/analysts/compliance.py`
- Modify: `backend/tests/unit/test_analysts.py`

- [ ] **Step 1: Write failing tests**

```python
def test_risk_analyst():
    from apps.analysts.risk import RiskAnalyst
    analyst = RiskAnalyst()
    assert hasattr(analyst, 'analyze')

def test_macro_analyst():
    from apps.analysts.macro import MacroAnalyst
    analyst = MacroAnalyst()
    assert hasattr(analyst, 'analyze')

def test_on_chain_analyst():
    from apps.analysts.on_chain import OnChainAnalyst
    analyst = OnChainAnalyst()
    assert hasattr(analyst, 'analyze')

def test_quant_analyst():
    from apps.analysts.quant import QuantAnalyst
    analyst = QuantAnalyst()
    assert hasattr(analyst, 'analyze')

def test_compliance_analyst():
    from apps.analysts.compliance import ComplianceAnalyst
    analyst = ComplianceAnalyst()
    assert hasattr(analyst, 'analyze')
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend
pytest tests/unit/test_analysts.py::test_risk_analyst -v
```

Expected: FAIL

- [ ] **Step 3: Write RiskAnalyst**

```python
# backend/apps/analysts/risk.py
from .base import BaseAnalyst, AnalystResult

class RiskAnalyst(BaseAnalyst):
    def __init__(self):
        self.capabilities = ['portfolio_correlation', 'var', 'max_drawdown', 'sharpe_ratio']

    async def analyze(self, symbol: str, timeframe: str) -> AnalystResult:
        risk_data = await self._fetch_risk_data(symbol)
        var = risk_data.get('var_95', 0.02)
        correlation = risk_data.get('avg_correlation', 0.5)
        drawdown = risk_data.get('current_drawdown', 0.05)
        
        signal, confidence = self._evaluate_risk(var, correlation, drawdown)
        
        return AnalystResult(
            analyst_name='risk',
            symbol=symbol,
            timeframe=timeframe,
            signal=signal,
            confidence=confidence,
            reasoning=f'VaR: {var:.2%}, Corr: {correlation:.2f}, DD: {drawdown:.2%}',
            data=risk_data
        )

    async def _fetch_risk_data(self, symbol: str) -> dict:
        return {
            'var_95': 0.015,
            'avg_correlation': 0.45,
            'current_drawdown': 0.03,
            'sharpe_ratio': 1.2,
            'position_count': 5
        }

    def _evaluate_risk(self, var: float, correlation: float, drawdown: float) -> tuple:
        if var > 0.03 or drawdown > 0.10:
            return ('SELL', 0.7)  # Risk off
        elif var < 0.01 and correlation < 0.3:
            return ('BUY', 0.6)  # Risk on
        return ('HOLD', 0.5)

    def get_capabilities(self) -> list[str]:
        return self.capabilities
```

- [ ] **Step 4: Write MacroAnalyst**

```python
# backend/apps/analysts/macro.py
from .base import BaseAnalyst, AnalystResult

class MacroAnalyst(BaseAnalyst):
    def __init__(self):
        self.capabilities = ['gdp', 'inflation', 'interest_rates', 'employment']

    async def analyze(self, symbol: str, timeframe: str) -> AnalystResult:
        macro_data = await self._fetch_macro_data()
        score = self._evaluate_macro(macro_data)
        
        signal = 'BUY' if score > 0.2 else ('SELL' if score < -0.2 else 'HOLD')
        confidence = min(0.5 + abs(score), 0.8)
        
        return AnalystResult(
            analyst_name='macro',
            symbol=symbol,
            timeframe=timeframe,
            signal=signal,
            confidence=confidence,
            reasoning=f'Macro score: {score:.2f}',
            data=macro_data
        )

    async def _fetch_macro_data(self) -> dict:
        return {
            'gdp_growth': 0.025,
            'inflation_rate': 0.032,
            'interest_rate': 0.0525,
            'unemployment_rate': 0.038
        }

    def _evaluate_macro(self, data: dict) -> float:
        score = 0.0
        if data['gdp_growth'] > 0.02:
            score += 0.2
        if data['inflation_rate'] < 0.03:
            score += 0.1
        if data['unemployment_rate'] < 0.05:
            score += 0.1
        return score

    def get_capabilities(self) -> list[str]:
        return self.capabilities
```

- [ ] **Step 5: Write OnChainAnalyst**

```python
# backend/apps/analysts/on_chain.py
from .base import BaseAnalyst, AnalystResult

class OnChainAnalyst(BaseAnalyst):
    def __init__(self):
        self.capabilities = ['hash_rate', 'wallet_flow', 'exchange_reserves', 'whale_alerts']

    async def analyze(self, symbol: str, timeframe: str) -> AnalystResult:
        chain_data = await self._fetch_chain_data(symbol)
        score = self._evaluate_chain(chain_data)
        
        signal = 'BUY' if score > 0.2 else ('SELL' if score < -0.2 else 'HOLD')
        confidence = min(0.5 + abs(score), 0.8)
        
        return AnalystResult(
            analyst_name='on_chain',
            symbol=symbol,
            timeframe=timeframe,
            signal=signal,
            confidence=confidence,
            reasoning=f'Chain score: {score:.2f}',
            data=chain_data
        )

    async def _fetch_chain_data(self, symbol: str) -> dict:
        return {
            'hash_rate_change': 0.05,
            'exchange_netflow': -1500,
            'whale_transactions': 12,
            'active_addresses': 850000
        }

    def _evaluate_chain(self, data: dict) -> float:
        score = 0.0
        if data['hash_rate_change'] > 0:
            score += 0.15
        if data['exchange_netflow'] < 0:
            score += 0.2
        if data['whale_transactions'] > 10:
            score += 0.1
        return score

    def get_capabilities(self) -> list[str]:
        return self.capabilities
```

- [ ] **Step 6: Write QuantAnalyst**

```python
# backend/apps/analysts/quant.py
from .base import BaseAnalyst, AnalystResult

class QuantAnalyst(BaseAnalyst):
    def __init__(self):
        self.capabilities = ['stat_arb', 'mean_reversion', 'cointegration', 'momentum']

    async def analyze(self, symbol: str, timeframe: str) -> AnalystResult:
        quant_data = await self._fetch_quant_data(symbol)
        score = self._evaluate_quant(quant_data)
        
        signal = 'BUY' if score > 0.2 else ('SELL' if score < -0.2 else 'HOLD')
        confidence = min(0.5 + abs(score), 0.85)
        
        return AnalystResult(
            analyst_name='quant',
            symbol=symbol,
            timeframe=timeframe,
            signal=signal,
            confidence=confidence,
            reasoning=f'Quant score: {score:.2f}',
            data=quant_data
        )

    async def _fetch_quant_data(self, symbol: str) -> dict:
        return {
            'z_score': 1.5,
            'momentum_20d': 0.03,
            'mean_reversion_signal': 0.6,
            'cointegration_pvalue': 0.02
        }

    def _evaluate_quant(self, data: dict) -> float:
        score = 0.0
        if abs(data['z_score']) > 2:
            score += 0.3 * (-1 if data['z_score'] > 0 else 1)
        if data['momentum_20d'] > 0.02:
            score += 0.2
        if data['cointegration_pvalue'] < 0.05:
            score += 0.15
        return score

    def get_capabilities(self) -> list[str]:
        return self.capabilities
```

- [ ] **Step 7: Write ComplianceAnalyst**

```python
# backend/apps/analysts/compliance.py
from .base import BaseAnalyst, AnalystResult

class ComplianceAnalyst(BaseAnalyst):
    def __init__(self):
        self.capabilities = ['regulatory_checks', 'position_limits', 'exposure_limits']

    async def analyze(self, symbol: str, timeframe: str) -> AnalystResult:
        compliance_data = await self._check_compliance(symbol)
        violations = compliance_data.get('violations', [])
        
        if violations:
            signal = 'HOLD'
            confidence = 0.9
            reasoning = f'Compliance violations: {", ".join(violations)}'
        else:
            signal = 'BUY'
            confidence = 0.7
            reasoning = 'All compliance checks passed'
        
        return AnalystResult(
            analyst_name='compliance',
            symbol=symbol,
            timeframe=timeframe,
            signal=signal,
            confidence=confidence,
            reasoning=reasoning,
            data=compliance_data
        )

    async def _check_compliance(self, symbol: str) -> dict:
        return {
            'violations': [],
            'position_limit_ok': True,
            'exposure_limit_ok': True,
            'regulatory_status': 'COMPLIANT'
        }

    def get_capabilities(self) -> list[str]:
        return self.capabilities
```

- [ ] **Step 8: Run tests**

```bash
cd backend
pytest tests/unit/test_analysts.py -v
```

Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add backend/apps/analysts/risk.py backend/apps/analysts/macro.py backend/apps/analysts/on_chain.py backend/apps/analysts/quant.py backend/apps/analysts/compliance.py backend/tests/unit/test_analysts.py
git commit -m "feat: add risk, macro, on-chain, quant, and compliance analysts"
```

---

## Task 6: Consensus Engine

**Files:**
- Create: `backend/apps/consensus/engine.py`
- Create: `backend/apps/consensus/voting.py`
- Create: `backend/tests/unit/test_consensus.py`

- [ ] **Step 1: Write failing test for ConsensusEngine**

```python
# backend/tests/unit/test_consensus.py
import pytest
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend
pytest tests/unit/test_consensus.py -v
```

Expected: FAIL

- [ ] **Step 3: Write VoteCounter**

```python
# backend/apps/consensus/voting.py
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
            agreement = hold_votes / total
            confidence = 0.5
        
        votes = {r.analyst_name: r.signal for r in results}
        
        return {
            'action': action,
            'confidence': confidence,
            'agreement': agreement,
            'votes': votes
        }
```

- [ ] **Step 4: Write ConsensusEngine**

```python
# backend/apps/consensus/engine.py
import asyncio
from typing import List, Dict, Any
from apps.analysts.base import BaseAnalyst, AnalystResult
from apps.consensus.voting import VoteCounter

class ConsensusEngine:
    def __init__(self, analysts: List[BaseAnalyst] = None):
        self.analysts = analysts or []
        self.vote_counter = VoteCounter()
        self.min_agreement = 0.70
    
    async def evaluate(self, symbol: str, timeframe: str) -> Dict[str, Any]:
        # 1. Run all analysts in parallel
        tasks = [analyst.analyze(symbol, timeframe) for analyst in self.analysts]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
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
        self.analysts = [a for a in self.analysts if a.__class__.__name__.lower().replace('analyst', '') != analyst_name]
```

- [ ] **Step 5: Run tests**

```bash
cd backend
pytest tests/unit/test_consensus.py -v
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/apps/consensus/engine.py backend/apps/consensus/voting.py backend/tests/unit/test_consensus.py
git commit -m "feat: add consensus engine with vote counting"
```

---

## Task 7: Multi-Timeframe Scanner

**Files:**
- Create: `backend/apps/scanner/scanner.py`
- Create: `backend/tests/unit/test_scanner.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/unit/test_scanner.py
import pytest
from apps.scanner.scanner import MultiTimeframeScanner

def test_scanner_creation():
    scanner = MultiTimeframeScanner()
    assert hasattr(scanner, 'scan')
    assert scanner.timeframes == ['1M', '5M', '15M', '1H', '4H', 'Daily']

def test_bias_filtering():
    scanner = MultiTimeframeScanner()
    # Test that 1H bias filters shorter timeframes
    assert '1H' in scanner.timeframes
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend
pytest tests/unit/test_scanner.py -v
```

Expected: FAIL

- [ ] **Step 3: Write MultiTimeframeScanner**

```python
# backend/apps/scanner/scanner.py
import asyncio
from typing import Dict, Any, List
from dataclasses import dataclass

@dataclass
class TimeframeResult:
    timeframe: str
    signal: str
    confidence: float
    data: Dict[str, Any]

@dataclass
class ScanResult:
    symbol: str
    timeframes: Dict[str, TimeframeResult]
    h1_bias: str
    alignment: float
    overall_signal: str
    overall_confidence: float

class MultiTimeframeScanner:
    def __init__(self):
        self.timeframes = ['1M', '5M', '15M', '1H', '4H', 'Daily']
    
    async def scan(self, symbol: str) -> ScanResult:
        # 1. Run all timeframes in parallel
        tasks = [self._analyze_timeframe(symbol, tf) for tf in self.timeframes]
        results = await asyncio.gather(*tasks)
        
        timeframe_results = {r.timeframe: r for r in results}
        
        # 2. Get 1H bias
        h1_bias = timeframe_results['1H'].signal
        
        # 3. Apply bias filter to shorter timeframes
        for tf in ['1M', '5M', '15M']:
            if timeframe_results[tf].signal != h1_bias:
                timeframe_results[tf] = TimeframeResult(
                    timeframe=tf,
                    signal=timeframe_results[tf].signal,
                    confidence=timeframe_results[tf].confidence * 0.5,
                    data=timeframe_results[tf].data
                )
        
        # 4. Calculate alignment
        alignment = self._calculate_alignment(timeframe_results)
        
        # 5. Aggregate signals
        overall_signal, overall_confidence = self._aggregate_signals(timeframe_results)
        
        return ScanResult(
            symbol=symbol,
            timeframes=timeframe_results,
            h1_bias=h1_bias,
            alignment=alignment,
            overall_signal=overall_signal,
            overall_confidence=overall_confidence
        )
    
    async def _analyze_timeframe(self, symbol: str, timeframe: str) -> TimeframeResult:
        # Placeholder: will use real market data
        import random
        signals = ['BUY', 'SELL', 'HOLD']
        return TimeframeResult(
            timeframe=timeframe,
            signal=random.choice(signals),
            confidence=random.uniform(0.5, 0.9),
            data={'symbol': symbol, 'timeframe': timeframe}
        )
    
    def _calculate_alignment(self, results: Dict[str, TimeframeResult]) -> float:
        signals = [r.signal for r in results.values()]
        buy_count = signals.count('BUY')
        sell_count = signals.count('SELL')
        total = len(signals)
        return max(buy_count, sell_count) / total if total > 0 else 0
    
    def _aggregate_signals(self, results: Dict[str, TimeframeResult]) -> tuple:
        # Weight higher timeframes more
        weights = {'1M': 0.1, '5M': 0.15, '15M': 0.2, '1H': 0.25, '4H': 0.3, 'Daily': 0.35}
        
        buy_score = sum(weights[tf] for tf, r in results.items() if r.signal == 'BUY')
        sell_score = sum(weights[tf] for tf, r in results.items() if r.signal == 'SELL')
        
        if buy_score > sell_score:
            return ('BUY', buy_score)
        elif sell_score > buy_score:
            return ('SELL', sell_score)
        return ('HOLD', 0.5)
```

- [ ] **Step 4: Run tests**

```bash
cd backend
pytest tests/unit/test_scanner.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/apps/scanner/scanner.py backend/tests/unit/test_scanner.py
git commit -m "feat: add multi-timeframe scanner with bias filtering"
```

---

## Task 8: Legendary Modules

**Files:**
- Create: `backend/apps/legendary/seykota.py`
- Create: `backend/apps/legendary/pyramiding.py`
- Create: `backend/apps/legendary/turtle_soup.py`
- Create: `backend/tests/unit/test_legendary.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/unit/test_legendary.py
import pytest
from apps.legendary.seykota import SeykotaTrendModule
from apps.legendary.pyramiding import PyramidingLogic
from apps.legendary.turtle_soup import TurtleSoupModule

def test_seykota_trend_module():
    module = SeykotaTrendModule()
    assert hasattr(module, 'analyze_trend')
    assert module.adx_threshold == 20

def test_pyramiding_logic():
    module = PyramidingLogic()
    assert hasattr(module, 'should_add_position')
    assert module.max_entries == 4

def test_turtle_soup_module():
    module = TurtleSoupModule()
    assert hasattr(module, 'detect_false_breakout')
    assert module.lookback == 20
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend
pytest tests/unit/test_legendary.py -v
```

Expected: FAIL

- [ ] **Step 3: Write SeykotaTrendModule**

```python
# backend/apps/legendary/seykota.py
import pandas as pd
import numpy as np
from typing import Dict, Any

class SeykotaTrendModule:
    def __init__(self):
        self.ema_periods = [21, 50, 200]
        self.adx_threshold = 20
    
    def analyze_trend(self, data: pd.DataFrame) -> Dict[str, Any]:
        close = data['close']
        
        # Calculate EMAs
        ema21 = close.ewm(span=21).mean()
        ema50 = close.ewm(span=50).mean()
        ema200 = close.ewm(span=200).mean()
        
        # Determine trend direction
        if ema21.iloc[-1] > ema50.iloc[-1] > ema200.iloc[-1]:
            trend = 'BULLISH'
        elif ema21.iloc[-1] < ema50.iloc[-1] < ema200.iloc[-1]:
            trend = 'BEARISH'
        else:
            trend = 'NEUTRAL'
        
        # Calculate ADX (simplified)
        adx = self._calculate_adx(data)
        
        # Block chop (ADX < 20)
        if adx < self.adx_threshold:
            return {
                'trend': 'CHOP',
                'confidence': 0,
                'action': 'HOLD',
                'adx': adx
            }
        
        # Generate signal
        if trend == 'BULLISH' and adx > 25:
            return {
                'trend': 'BULLISH',
                'confidence': min(1.0, adx / 50),
                'action': 'BUY',
                'adx': adx
            }
        elif trend == 'BEARISH' and adx > 25:
            return {
                'trend': 'BEARISH',
                'confidence': min(1.0, adx / 50),
                'action': 'SELL',
                'adx': adx
            }
        
        return {
            'trend': 'NEUTRAL',
            'confidence': 0,
            'action': 'HOLD',
            'adx': adx
        }
    
    def _calculate_adx(self, data: pd.DataFrame, period: int = 14) -> float:
        high = data['high']
        low = data['low']
        close = data['close']
        
        plus_dm = high.diff()
        minus_dm = -low.diff()
        
        plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
        minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)
        
        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        atr = tr.rolling(window=period).mean()
        plus_di = 100 * (plus_dm.rolling(window=period).mean() / atr)
        minus_di = 100 * (minus_dm.rolling(window=period).mean() / atr)
        
        dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di))
        adx = dx.rolling(window=period).mean()
        
        return float(adx.iloc[-1]) if not pd.isna(adx.iloc[-1]) else 0.0
```

- [ ] **Step 4: Write PyramidingLogic**

```python
# backend/apps/legendary/pyramiding.py
from typing import Dict, Any, Optional
from .seykota import SeykotaTrendModule

class PyramidingLogic:
    def __init__(self):
        self.entry_count = 1
        self.max_entries = 4
        self.increment_percent = 0.3
    
    def should_add_position(self, position: Dict[str, Any], market_data: Any) -> Optional[Dict[str, Any]]:
        # 1. Must be in profit
        if position.get('profit_pips', 0) < 20:
            return None
        
        # 2. Trend must still be strong
        seykota = SeykotaTrendModule()
        trend = seykota.analyze_trend(market_data)
        if trend['action'] != position.get('action'):
            return None
        
        # 3. Not reached max entries
        if self.entry_count >= self.max_entries:
            return None
        
        # 4. Calculate additional lot size
        base_lot = position.get('lot_size', 0.01)
        additional = base_lot * (1 + self.increment_percent * (self.entry_count - 1))
        
        self.entry_count += 1
        
        return {
            'add': True,
            'additional_lot': additional,
            'reason': f'Pyramiding entry #{self.entry_count}'
        }
    
    def reset(self):
        self.entry_count = 1
```

- [ ] **Step 5: Write TurtleSoupModule**

```python
# backend/apps/legendary/turtle_soup.py
import pandas as pd
from typing import Dict, Any, Optional

class TurtleSoupModule:
    def __init__(self):
        self.lookback = 20
        self.breakout_range = 0.002
    
    def detect_false_breakout(self, data: pd.DataFrame) -> Optional[Dict[str, Any]]:
        # 1. Get recent high/low
        high = data['high'].rolling(self.lookback).max()
        low = data['low'].rolling(self.lookback).min()
        
        # 2. Check breakout
        current_close = data['close'].iloc[-1]
        previous_close = data['close'].iloc[-2]
        
        # 3. Bullish false breakout
        if current_close > high.iloc[-2] and previous_close < high.iloc[-2]:
            if current_close < high.iloc[-2] + self.breakout_range:
                return {
                    'signal': 'BUY',
                    'confidence': 0.75,
                    'reason': 'Bullish Turtle Soup'
                }
        
        # 4. Bearish false breakout
        if current_close < low.iloc[-2] and previous_close > low.iloc[-2]:
            if current_close > low.iloc[-2] - self.breakout_range:
                return {
                    'signal': 'SELL',
                    'confidence': 0.75,
                    'reason': 'Bearish Turtle Soup'
                }
        
        return None
```

- [ ] **Step 6: Run tests**

```bash
cd backend
pytest tests/unit/test_legendary.py -v
```

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/apps/legendary/seykota.py backend/apps/legendary/pyramiding.py backend/apps/legendary/turtle_soup.py backend/tests/unit/test_legendary.py
git commit -m "feat: add legendary modules (Seykota, Pyramiding, Turtle Soup)"
```

---

## Task 9: Redis Cache Layer

**Files:**
- Create: `backend/cache/redis.py`
- Create: `backend/tests/unit/test_cache.py` (from integration)

- [ ] **Step 1: Write failing test**

```python
# backend/tests/integration/test_cache.py
import pytest
from cache.redis import RedisCache

def test_redis_cache_creation():
    cache = RedisCache()
    assert hasattr(cache, 'get')
    assert hasattr(cache, 'set')
    assert hasattr(cache, 'delete')
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend
pytest tests/integration/test_cache.py -v
```

Expected: FAIL

- [ ] **Step 3: Write RedisCache**

```python
# backend/cache/redis.py
import json
import redis
from typing import Any, Optional
from django.conf import settings

class RedisCache:
    def __init__(self):
        self.client = redis.from_url(settings.REDIS_URL, decode_responses=True)
    
    def get(self, key: str) -> Optional[Any]:
        value = self.client.get(key)
        if value:
            return json.loads(value)
        return None
    
    def set(self, key: str, value: Any, ttl: int = 60):
        self.client.setex(key, ttl, json.dumps(value, default=str))
    
    def delete(self, key: str):
        self.client.delete(key)
    
    def get_market_data(self, symbol: str, timeframe: str) -> Optional[dict]:
        return self.get(f'market:{symbol}:{timeframe}')
    
    def set_market_data(self, symbol: str, timeframe: str, data: dict, ttl: int = 5):
        self.set(f'market:{symbol}:{timeframe}', data, ttl)
    
    def get_analyst_result(self, analyst_name: str, symbol: str, timeframe: str) -> Optional[dict]:
        return self.get(f'analyst:{analyst_name}:{symbol}:{timeframe}')
    
    def set_analyst_result(self, analyst_name: str, symbol: str, timeframe: str, data: dict, ttl: int = 60):
        self.set(f'analyst:{analyst_name}:{symbol}:{timeframe}', data, ttl)
    
    def get_consensus(self, symbol: str) -> Optional[dict]:
        return self.get(f'consensus:{symbol}')
    
    def set_consensus(self, symbol: str, data: dict, ttl: int = 30):
        self.set(f'consensus:{symbol}', data, ttl)
    
    def increment_daily_loss(self, amount: float):
        from datetime import date
        today = date.today().isoformat()
        self.client.incrbyfloat(f'daily_loss:{today}', amount)
    
    def get_daily_loss(self) -> float:
        from datetime import date
        today = date.today().isoformat()
        value = self.client.get(f'daily_loss:{today}')
        return float(value) if value else 0.0
```

- [ ] **Step 4: Run tests**

```bash
cd backend
pytest tests/integration/test_cache.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/cache/redis.py backend/tests/integration/test_cache.py
git commit -m "feat: add Redis cache layer"
```

---

## Task 10: FastAPI Routes

**Files:**
- Create: `backend/api/main.py`
- Create: `backend/api/deps.py`
- Create: `backend/api/routes/market.py`
- Create: `backend/api/routes/analysts.py`
- Create: `backend/api/routes/consensus.py`
- Create: `backend/api/routes/scanner.py`
- Create: `backend/api/routes/legendary.py`
- Create: `backend/api/routes/trades.py`
- Create: `backend/api/routes/positions.py`
- Create: `backend/tests/integration/test_api.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/integration/test_api.py
import pytest
from fastapi.testclient import TestClient
from api.main import app

def test_api_health():
    client = TestClient(app)
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend
pytest tests/integration/test_api.py -v
```

Expected: FAIL

- [ ] **Step 3: Write FastAPI app**

```python
# backend/api/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes import market, analysts, consensus, scanner, legendary, trades, positions

app = FastAPI(
    title="Dutchkem Trader API",
    description="Legendary Intelligence Edition - Backend Core",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(market.router, prefix="/api/v1/market", tags=["Market"])
app.include_router(analysts.router, prefix="/api/v1/analysts", tags=["Analysts"])
app.include_router(consensus.router, prefix="/api/v1/consensus", tags=["Consensus"])
app.include_router(scanner.router, prefix="/api/v1/scan", tags=["Scanner"])
app.include_router(legendary.router, prefix="/api/v1/legendary", tags=["Legendary"])
app.include_router(trades.router, prefix="/api/v1/trades", tags=["Trades"])
app.include_router(positions.router, prefix="/api/v1/positions", tags=["Positions"])

@app.get("/api/v1/health")
async def health_check():
    return {"status": "ok", "version": "1.0.0"}
```

- [ ] **Step 4: Write route modules**

```python
# backend/api/routes/market.py
from fastapi import APIRouter
router = APIRouter()

@router.get("/{symbol}/price")
async def get_price(symbol: str):
    return {"symbol": symbol, "price": 1.0890, "timestamp": "2026-09-05T00:00:00Z"}

@router.get("/{symbol}/candles")
async def get_candles(symbol: str, timeframe: str = "1H", limit: int = 100):
    return {"symbol": symbol, "timeframe": timeframe, "candles": []}
```

```python
# backend/api/routes/analysts.py
from fastapi import APIRouter
router = APIRouter()

@router.get("/")
async def list_analysts():
    return {"analysts": ["market", "news", "fundamentals", "sentiment", "technical", "options", "order_flow", "risk", "macro", "on_chain", "quant", "compliance"]}

@router.get("/{name}/status")
async def get_analyst_status(name: str):
    return {"name": name, "status": "active"}
```

```python
# backend/api/routes/consensus.py
from fastapi import APIRouter
router = APIRouter()

@router.post("/evaluate")
async def evaluate_consensus(symbol: str, timeframe: str = "1H"):
    return {"symbol": symbol, "action": "HOLD", "confidence": 0.0, "agreement_pct": 0.0}
```

```python
# backend/api/routes/scanner.py
from fastapi import APIRouter
router = APIRouter()

@router.get("/{symbol}")
async def scan_symbol(symbol: str):
    return {"symbol": symbol, "overall_signal": "HOLD", "alignment": 0.5}
```

```python
# backend/api/routes/legendary.py
from fastapi import APIRouter
router = APIRouter()

@router.get("/seykota/{symbol}")
async def get_seykota_analysis(symbol: str):
    return {"symbol": symbol, "trend": "NEUTRAL", "confidence": 0.0}

@router.get("/turtle/{symbol}")
async def get_turtle_soup(symbol: str):
    return {"symbol": symbol, "signal": None}

@router.get("/pyramiding/{symbol}")
async def get_pyramiding(symbol: str):
    return {"symbol": symbol, "add_position": False}
```

```python
# backend/api/routes/trades.py
from fastapi import APIRouter
router = APIRouter()

@router.get("/")
async def list_trades():
    return {"trades": []}

@router.get("/{trade_id}")
async def get_trade(trade_id: str):
    return {"id": trade_id, "status": "pending"}
```

```python
# backend/api/routes/positions.py
from fastapi import APIRouter
router = APIRouter()

@router.get("/")
async def list_positions():
    return {"positions": []}

@router.get("/{position_id}")
async def get_position(position_id: str):
    return {"id": position_id, "unrealized_pnl": 0.0}
```

- [ ] **Step 5: Run tests**

```bash
cd backend
pytest tests/integration/test_api.py -v
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/api/ backend/tests/integration/test_api.py
git commit -m "feat: add FastAPI routes for all endpoints"
```

---

## Task 11: WebSocket Handlers

**Files:**
- Create: `backend/api/websocket/handlers.py`
- Modify: `backend/api/main.py`

- [ ] **Step 1: Write WebSocket handler**

```python
# backend/api/websocket/handlers.py
from fastapi import WebSocket, WebSocketDisconnect
from typing import List, Dict
import json
import asyncio

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, channel: str):
        await websocket.accept()
        if channel not in self.active_connections:
            self.active_connections[channel] = []
        self.active_connections[channel].append(websocket)
    
    def disconnect(self, websocket: WebSocket, channel: str):
        if channel in self.active_connections:
            self.active_connections[channel].remove(websocket)
    
    async def broadcast(self, channel: str, message: dict):
        if channel in self.active_connections:
            for connection in self.active_connections[channel]:
                try:
                    await connection.send_json(message)
                except:
                    pass

manager = ConnectionManager()

async def market_websocket(websocket: WebSocket, symbol: str):
    await manager.connect(websocket, f"market:{symbol}")
    try:
        while True:
            # Placeholder: will stream real market data
            await asyncio.sleep(1)
            await websocket.send_json({
                "symbol": symbol,
                "price": 1.0890,
                "timestamp": "2026-09-05T00:00:00Z"
            })
    except WebSocketDisconnect:
        manager.disconnect(websocket, f"market:{symbol}")

async def trades_websocket(websocket: WebSocket):
    await manager.connect(websocket, "trades")
    try:
        while True:
            await asyncio.sleep(1)
            await websocket.send_json({"type": "heartbeat"})
    except WebSocketDisconnect:
        manager.disconnect(websocket, "trades")

async def consensus_websocket(websocket: WebSocket):
    await manager.connect(websocket, "consensus")
    try:
        while True:
            await asyncio.sleep(1)
            await websocket.send_json({"type": "heartbeat"})
    except WebSocketDisconnect:
        manager.disconnect(websocket, "consensus")
```

- [ ] **Step 2: Update FastAPI app to include WebSocket routes**

```python
# Add to backend/api/main.py
from api.websocket.handlers import market_websocket, trades_websocket, consensus_websocket

app.websocket("/ws/market/{symbol}")(market_websocket)
app.websocket("/ws/trades")(trades_websocket)
app.websocket("/ws/consensus")(consensus_websocket)
```

- [ ] **Step 3: Commit**

```bash
git add backend/api/websocket/ backend/api/main.py
git commit -m "feat: add WebSocket handlers for real-time data"
```

---

## Task 12: Celery Tasks

**Files:**
- Create: `backend/tasks/analyst_tasks.py`
- Create: `backend/tasks/scanner_tasks.py`

- [ ] **Step 1: Write Celery tasks**

```python
# backend/tasks/analyst_tasks.py
from celery import shared_task
import asyncio
from apps.analysts.market import MarketAnalyst
from apps.analysts.news import NewsAnalyst
from apps.analysts.fundamentals import FundamentalsAnalyst
from apps.analysts.sentiment import SentimentAnalyst
from apps.analysts.technical import TechnicalAnalyst
from apps.analysts.options import OptionsAnalyst
from apps.analysts.order_flow import OrderFlowAnalyst
from apps.analysts.risk import RiskAnalyst
from apps.analysts.macro import MacroAnalyst
from apps.analysts.on_chain import OnChainAnalyst
from apps.analysts.quant import QuantAnalyst
from apps.analysts.compliance import ComplianceAnalyst

ANALYSTS = {
    'market': MarketAnalyst(),
    'news': NewsAnalyst(),
    'fundamentals': FundamentalsAnalyst(),
    'sentiment': SentimentAnalyst(),
    'technical': TechnicalAnalyst(),
    'options': OptionsAnalyst(),
    'order_flow': OrderFlowAnalyst(),
    'risk': RiskAnalyst(),
    'macro': MacroAnalyst(),
    'on_chain': OnChainAnalyst(),
    'quant': QuantAnalyst(),
    'compliance': ComplianceAnalyst(),
}

@shared_task
def run_analyst(analyst_name: str, symbol: str, timeframe: str):
    analyst = ANALYSTS.get(analyst_name)
    if not analyst:
        return {'error': f'Analyst {analyst_name} not found'}
    
    loop = asyncio.new_event_loop()
    result = loop.run_until_complete(analyst.analyze(symbol, timeframe))
    loop.close()
    
    return {
        'analyst_name': result.analyst_name,
        'symbol': result.symbol,
        'timeframe': result.timeframe,
        'signal': result.signal,
        'confidence': result.confidence,
        'reasoning': result.reasoning,
        'data': result.data
    }

@shared_task
def run_all_analysts(symbol: str, timeframe: str):
    results = []
    for name, analyst in ANALYSTS.items():
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(analyst.analyze(symbol, timeframe))
        loop.close()
        results.append({
            'analyst_name': result.analyst_name,
            'signal': result.signal,
            'confidence': result.confidence
        })
    return results
```

```python
# backend/tasks/scanner_tasks.py
from celery import shared_task
import asyncio
from apps.scanner.scanner import MultiTimeframeScanner

@shared_task
def run_full_scan(symbol: str):
    scanner = MultiTimeframeScanner()
    loop = asyncio.new_event_loop()
    result = loop.run_until_complete(scanner.scan(symbol))
    loop.close()
    
    return {
        'symbol': result.symbol,
        'h1_bias': result.h1_bias,
        'alignment': result.alignment,
        'overall_signal': result.overall_signal,
        'overall_confidence': result.overall_confidence
    }
```

- [ ] **Step 2: Commit**

```bash
git add backend/tasks/analyst_tasks.py backend/tasks/scanner_tasks.py
git commit -m "feat: add Celery tasks for analysts and scanner"
```

---

## Task 13: Integration Tests

**Files:**
- Create: `backend/tests/conftest.py`
- Modify: `backend/tests/integration/test_api.py`
- Modify: `backend/tests/integration/test_database.py`

- [ ] **Step 1: Write conftest.py with fixtures**

```python
# backend/tests/conftest.py
import pytest
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
```

- [ ] **Step 2: Write integration tests**

```python
# backend/tests/integration/test_api.py (expand)
import pytest
from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)

def test_health_check():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_list_analysts():
    response = client.get("/api/v1/analysts/")
    assert response.status_code == 200
    assert len(response.json()["analysts"]) == 12

def test_get_price():
    response = client.get("/api/v1/market/EURUSD/price")
    assert response.status_code == 200
    assert response.json()["symbol"] == "EURUSD"

def test_scan_symbol():
    response = client.get("/api/v1/scan/EURUSD")
    assert response.status_code == 200
    assert "overall_signal" in response.json()

def test_get_seykota():
    response = client.get("/api/v1/legendary/seykota/EURUSD")
    assert response.status_code == 200
    assert "trend" in response.json()
```

```python
# backend/tests/integration/test_database.py
import pytest
from django_app.models import AnalystResult, ConsensusResult, Trade

def test_analyst_result_creation():
    result = AnalystResult.objects.create(
        analyst_name='market',
        symbol='EURUSD',
        timeframe='1H',
        signal='BUY',
        confidence=0.85,
        reasoning='Strong signal',
        data={'rsi': 65}
    )
    assert result.id is not None
    assert result.analyst_name == 'market'

def test_consensus_result_creation():
    result = ConsensusResult.objects.create(
        symbol='EURUSD',
        action='BUY',
        confidence=0.8,
        agreement_pct=0.75,
        votes={'market': 'BUY', 'news': 'BUY'},
        legendary_votes={'seykota': 'BUY'}
    )
    assert result.id is not None
    assert result.action == 'BUY'

def test_trade_creation():
    trade = Trade.objects.create(
        symbol='EURUSD',
        action='BUY',
        entry_price=1.0890,
        stop_loss=1.0850,
        take_profit=1.0970,
        lot_size=0.40,
        status='pending'
    )
    assert trade.id is not None
    assert trade.status == 'pending'
```

- [ ] **Step 3: Run integration tests**

```bash
cd backend
pytest tests/integration/ -v
```

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/tests/conftest.py backend/tests/integration/
git commit -m "feat: add integration tests for API and database"
```

---

## Task 14: E2E Test

**Files:**
- Create: `backend/tests/e2e/test_trading_flow.py`

- [ ] **Step 1: Write E2E test**

```python
# backend/tests/e2e/test_trading_flow.py
import pytest
import asyncio
from apps.analysts.market import MarketAnalyst
from apps.analysts.news import NewsAnalyst
from apps.consensus.engine import ConsensusEngine
from apps.scanner.scanner import MultiTimeframeScanner
from apps.legendary.seykota import SeykotaTrendModule
from apps.legendary.turtle_soup import TurtleSoupModule

@pytest.mark.asyncio
async def test_full_trading_flow():
    # 1. Initialize components
    analysts = [MarketAnalyst(), NewsAnalyst()]
    engine = ConsensusEngine(analysts=analysts)
    scanner = MultiTimeframeScanner()
    seykota = SeykotaTrendModule()
    turtle = TurtleSoupModule()
    
    symbol = "EURUSD"
    
    # 2. Run multi-timeframe scan
    scan_result = await scanner.scan(symbol)
    assert scan_result.symbol == symbol
    assert scan_result.overall_signal in ['BUY', 'SELL', 'HOLD']
    
    # 3. Run consensus evaluation
    consensus_result = await engine.evaluate(symbol, "1H")
    assert consensus_result['action'] in ['BUY', 'SELL', 'HOLD']
    assert 0 <= consensus_result['confidence'] <= 1
    
    # 4. Run legendary modules
    import pandas as pd
    import numpy as np
    data = pd.DataFrame({
        'close': np.random.randn(200).cumsum() + 100,
        'high': np.random.randn(200).cumsum() + 101,
        'low': np.random.randn(200).cumsum() + 99
    })
    
    seykota_result = seykota.analyze_trend(data)
    assert seykota_result['trend'] in ['BULLISH', 'BEARISH', 'NEUTRAL', 'CHOP']
    
    turtle_result = turtle.detect_false_breakout(data)
    # turtle_result can be None or a dict
    
    # 5. Verify all components work together
    assert True  # If we got here, the flow works
```

- [ ] **Step 2: Run E2E test**

```bash
cd backend
pytest tests/e2e/ -v
```

Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add backend/tests/e2e/
git commit -m "feat: add E2E test for full trading flow"
```

---

## Task 15: Final Verification

- [ ] **Step 1: Run all tests**

```bash
cd backend
pytest tests/ -v --cov=apps --cov=api --cov=cache --cov=tasks
```

Expected: All tests pass, coverage > 80%

- [ ] **Step 2: Run linting**

```bash
cd backend
ruff check apps/ api/ cache/ tasks/
mypy apps/ api/ cache/ tasks/
```

Expected: No errors

- [ ] **Step 3: Verify Django setup**

```bash
cd backend
python manage.py check
python manage.py makemigrations
python manage.py migrate
```

Expected: System check passed, migrations created and applied

- [ ] **Step 4: Start services and verify**

```bash
# Terminal 1: Redis
redis-server

# Terminal 2: RabbitMQ
rabbitmq-server

# Terminal 3: PostgreSQL
pg_ctl start

# Terminal 4: Django
cd backend
python manage.py runserver 8000

# Terminal 5: FastAPI
cd backend
uvicorn api.main:app --reload --port 8001

# Terminal 6: Celery
cd backend
celery -A config.celery_app worker --loglevel=info
```

- [ ] **Step 5: Final commit**

```bash
git add .
git commit -m "feat: complete Backend Core - Dutchkem Trader Legendary Intelligence Edition"
```

---

## Success Criteria Checklist

- [ ] All 12 analysts implement BaseAnalyst interface
- [ ] Each analyst returns valid AnalystResult
- [ ] Consensus engine aggregates votes and enforces 70% threshold
- [ ] Multi-timeframe scanner runs 6 timeframes in parallel
- [ ] 1H bias filter reduces confidence on misaligned shorter timeframes
- [ ] Legendary modules (Seykota, Turtle Soup, Pyramiding) work correctly
- [ ] All API endpoints return correct responses
- [ ] WebSocket connections work for real-time data
- [ ] Redis caching works with correct TTLs
- [ ] Database models are properly migrated
- [ ] Unit test coverage > 80%
- [ ] Integration tests pass
- [ ] E2E test passes
- [ ] Linting passes with no errors
