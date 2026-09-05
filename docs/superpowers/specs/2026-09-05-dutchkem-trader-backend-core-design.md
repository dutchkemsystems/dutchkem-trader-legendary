# Dutchkem Trader — Backend Core Design Spec

**Date:** 2026-09-05
**Sub-Project:** Backend Core (1 of 8)
**Status:** Approved
**Version:** 1.0

---

## Overview

Build the Backend Core of Dutchkem Trader — the AI trading engine that runs 12 analysts in parallel, aggregates their signals through a consensus engine, and produces trade signals with legendary module integration.

## Non-Goals (This Sub-Project)

- Frontend web/mobile UI (Sub-Project 5/6)
- Voice synthesis (Sub-Project 7)
- Telegram bot (Sub-Project 7)
- Eye tracking (Sub-Project 8)
- Order execution (Sub-Project 2)
- Broker integration (Sub-Project 4)
- Walk-forward optimization (Sub-Project 4)

## Architecture

### Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| API Framework | FastAPI | Async trading API, WebSocket, OpenAPI docs |
| Admin/Auth | Django | ORM, admin panel, user management |
| Database | PostgreSQL | Trade data, analyst results, positions, audit logs |
| Cache | Redis | Real-time market data, analyst cache, pub/sub |
| Task Queue | Celery + RabbitMQ | Async analyst runs, scheduled scans |

### Data Flow

```
Market Data Feed → 12 Analysts (parallel) → Consensus Engine → Legendary Modules → Risk Check → Execution Signal
```

### Key Design Decisions

1. Each analyst is a standalone module with a common interface
2. Consensus engine runs async and aggregates all analyst results
3. Legendary modules (Seykota, Turtle Soup, Pyramiding) are plugins to the consensus engine
4. All trades go through risk validation before execution
5. Redis caching with appropriate TTLs for real-time performance

---

## Components

### 1. 12 Analyst Team

Each analyst follows a common interface:

```python
class BaseAnalyst(ABC):
    @abstractmethod
    async def analyze(self, symbol: str, timeframe: str) -> AnalystResult:
        pass
    
    @abstractmethod
    def get_capabilities(self) -> list[str]:
        pass
```

**AnalystResult structure:**

```python
class AnalystResult(BaseModel):
    analyst_name: str
    symbol: str
    timeframe: str
    signal: Literal["BUY", "SELL", "HOLD"]
    confidence: float  # 0.0 - 1.0
    reasoning: str
    data: dict
    timestamp: datetime
```

**The 12 Analysts:**

| # | Analyst | Primary Tools | Data Sources |
|---|---------|---------------|--------------|
| 1 | Market | RSI, MACD, BB, ATR, Stochastic, Ichimoku, Fibonacci, VWAP | Price feeds |
| 2 | News | Sentiment scoring, keyword extraction, event detection | News API |
| 3 | Fundamentals | P/E ratio, P/B ratio, ROE, debt-to-equity, cash flow | Financial APIs |
| 4 | Sentiment | Social media NLP, Fear/Greed index, positioning data | Twitter, Reddit, Fear/Greed API |
| 5 | Technical | Chart pattern recognition, support/resistance | GPT-4V/Claude Vision |
| 6 | Options | IV analysis, Put/Call ratio, Greeks, unusual activity | Options data API |
| 7 | Order Flow | Microprice, liquidity imbalance, CVD, trade flow | Order book data |
| 8 | Risk | Portfolio correlation, VaR, max drawdown, Sharpe | Internal portfolio data |
| 9 | Macro | GDP, inflation, interest rates, employment | Economic data APIs |
| 10 | On-Chain | Hash rate, wallet flow, exchange reserves, whale alerts | On-chain APIs |
| 11 | Quant | Statistical arbitrage, mean reversion, cointegration | Internal quant models |
| 12 | Compliance | Regulatory checks, position limits, exposure limits | Compliance rules DB |

Each analyst runs independently and in parallel via Celery tasks.

### 2. Consensus Engine

The consensus engine aggregates all analyst results and decides whether to trade.

**Voting System (7 conditions must pass):**

```python
class ConsensusEngine:
    async def evaluate(self, symbol: str, timeframe: str) -> ConsensusResult:
        # 1. Run all 12 analysts in parallel
        analyst_results = await asyncio.gather(*[
            analyst.analyze(symbol, timeframe) 
            for analyst in self.analysts
        ])
        
        # 2. ML Model vote (LightGBM/XGBoost)
        ml_vote = await self.ml_model.predict(symbol)
        
        # 3. Legendary module votes
        seykota_vote = await self.seykota_module.analyze(market_data)
        turtle_soup_vote = await self.turtle_soup_module.detect_false_breakout(market_data)
        
        # 4. Aggregate votes
        votes = self._count_votes(analyst_results, ml_vote, seykota_vote, turtle_soup_vote)
        
        # 5. Require 70%+ agreement
        if votes['agreement'] < 0.70:
            return ConsensusResult(action="HOLD", reason="Insufficient agreement")
        
        # 6. Return consensus signal
        return ConsensusResult(
            action=votes['action'],
            confidence=votes['confidence'],
            votes=votes
        )
```

**ConsensusResult structure:**

```python
class ConsensusResult(BaseModel):
    action: Literal["BUY", "SELL", "HOLD"]
    confidence: float
    agreement_pct: float
    votes: dict
    legendary_votes: dict
    timestamp: datetime
```

### 3. Multi-Timeframe Scanner

Scans across 6 timeframes with bias filtering.

**Timeframes:**

| Timeframe | Purpose | Usage |
|-----------|---------|-------|
| 1 Minute | Entry timing | Precise entry points |
| 5 Minutes | Short-term momentum | Quick trades |
| 15 Minutes | Intraday trend | Intraday bias |
| 1 Hour | Medium-term bias | Bias filter for shorter timeframes |
| 4 Hours | Major trend | Trend direction |
| Daily | Long-term direction | Strategic direction |

**Bias Filtering Logic:**

```python
class MultiTimeframeScanner:
    async def scan(self, symbol: str) -> ScanResult:
        # 1. Run all timeframes in parallel
        timeframe_results = await asyncio.gather(*[
            self._analyze_timeframe(symbol, tf) 
            for tf in TIMEFRAMES
        ])
        
        # 2. Get 1H bias
        h1_bias = timeframe_results['1H'].signal
        
        # 3. Apply bias filter to shorter timeframes
        for tf in ['1M', '5M', '15M']:
            if timeframe_results[tf].signal != h1_bias:
                timeframe_results[tf].confidence *= 0.5
        
        # 4. Align with higher timeframes
        alignment = self._check_alignment(timeframe_results)
        
        return ScanResult(
            symbol=symbol,
            timeframes=timeframe_results,
            h1_bias=h1_bias,
            alignment=alignment,
            overall_signal=self._aggregate_signals(timeframe_results)
        )
```

### 4. Database Models

**Core Models (PostgreSQL):**

```python
# User & Auth
class User(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    email = models.EmailField(unique=True)
    password_hash = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

# Analyst Results
class AnalystResult(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    analyst_name = models.CharField(max_length=50)
    symbol = models.CharField(max_length=20)
    timeframe = models.CharField(max_length=10)
    signal = models.CharField(max_length=10)
    confidence = models.FloatField()
    reasoning = models.TextField()
    data = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

# Consensus Results
class ConsensusResult(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    symbol = models.CharField(max_length=20)
    action = models.CharField(max_length=10)
    confidence = models.FloatField()
    agreement_pct = models.FloatField()
    votes = models.JSONField()
    legendary_votes = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

# Trades
class Trade(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    symbol = models.CharField(max_length=20)
    action = models.CharField(max_length=10)
    entry_price = models.DecimalField(max_digits=20, decimal_places=8)
    stop_loss = models.DecimalField(max_digits=20, decimal_places=8)
    take_profit = models.DecimalField(max_digits=20, decimal_places=8)
    lot_size = models.DecimalField(max_digits=10, decimal_places=4)
    status = models.CharField(max_length=20)
    pnl = models.DecimalField(max_digits=20, decimal_places=8, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

# Positions
class Position(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    trade = models.OneToOneField(Trade, on_delete=models.CASCADE)
    current_price = models.DecimalField(max_digits=20, decimal_places=8)
    unrealized_pnl = models.DecimalField(max_digits=20, decimal_places=8)
    updated_at = models.DateTimeField(auto_now=True)

# Legendary Module Results
class LegendaryModuleResult(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    module_name = models.CharField(max_length=50)
    symbol = models.CharField(max_length=20)
    signal = models.CharField(max_length=10)
    confidence = models.FloatField()
    data = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
```

**Redis Cache Keys:**

```
market:{symbol}:{timeframe}     → Latest price data (TTL: 5s)
analyst:{name}:{symbol}:{tf}    → Latest analyst result (TTL: 60s)
consensus:{symbol}              → Latest consensus (TTL: 30s)
positions:active                 → Active positions (TTL: none)
daily_loss:{date}               → Daily loss total (TTL: end of day)
```

### 5. API Endpoints

**FastAPI Endpoints:**

```
# Market Data
GET  /api/v1/market/{symbol}/price
GET  /api/v1/market/{symbol}/candles
GET  /api/v1/market/{symbol}/orderbook

# Analysts
GET  /api/v1/analysts
GET  /api/v1/analysts/{name}/status
POST /api/v1/analysts/{name}/run
GET  /api/v1/analysts/results/{symbol}

# Consensus
POST /api/v1/consensus/evaluate
GET  /api/v1/consensus/{symbol}/latest
GET  /api/v1/consensus/history

# Multi-Timeframe
GET  /api/v1/scan/{symbol}
GET  /api/v1/scan/{symbol}/timeframe/{tf}

# Legendary Modules
GET  /api/v1/legendary/seykota/{symbol}
GET  /api/v1/legendary/turtle/{symbol}
GET  /api/v1/legendary/pyramiding/{symbol}

# Trades
GET  /api/v1/trades
GET  /api/v1/trades/{id}
POST /api/v1/trades
DELETE /api/v1/trades/{id}

# Positions
GET  /api/v1/positions
GET  /api/v1/positions/{id}
POST /api/v1/positions/{id}/close

# WebSocket
WS   /ws/market/{symbol}
WS   /ws/trades
WS   /ws/consensus
```

**Django Admin:** Available at `/admin/` for user management, analyst config, trade history review.

---

## Testing Strategy

### Test Pyramid

| Level | Count | Focus |
|-------|-------|-------|
| Unit Tests | ~60% | Individual analyst logic, consensus voting, risk calculations |
| Integration Tests | ~30% | API endpoints, database queries, Redis caching |
| E2E Tests | ~10% | Full trading flow from signal to execution |

### Key Test Scenarios

**Unit Tests:**
- Each analyst returns correct signal format
- Consensus engine correctly aggregates votes
- Multi-timeframe bias filtering works
- Risk calculations (position sizing, R:R ratio)

**Integration Tests:**
- POST /api/v1/consensus/evaluate returns valid ConsensusResult
- WebSocket connects and receives market data
- Analyst results cached in Redis with correct TTL
- Trade creation validates risk rules

**E2E Tests:**
- Full scan → consensus → trade creation flow
- Position open → monitoring → close flow
- Daily loss limit enforcement

### Test Commands

```bash
pytest tests/unit/ -v
pytest tests/integration/ -v --db=postgresql
pytest --cov=backend --cov-report=html
ruff check backend/
mypy backend/
```

---

## Project Structure

```
backend/
├── apps/
│   ├── analysts/           # 12 Analyst modules
│   │   ├── __init__.py
│   │   ├── base.py         # BaseAnalyst ABC
│   │   ├── market.py
│   │   ├── news.py
│   │   ├── fundamentals.py
│   │   ├── sentiment.py
│   │   ├── technical.py
│   │   ├── options.py
│   │   ├── order_flow.py
│   │   ├── risk.py
│   │   ├── macro.py
│   │   ├── on_chain.py
│   │   ├── quant.py
│   │   └── compliance.py
│   ├── consensus/          # Consensus Engine
│   │   ├── __init__.py
│   │   ├── engine.py
│   │   └── voting.py
│   ├── scanner/            # Multi-Timeframe Scanner
│   │   ├── __init__.py
│   │   └── scanner.py
│   └── legendary/          # Legendary Modules
│       ├── __init__.py
│       ├── seykota.py
│       ├── pyramiding.py
│       └── turtle_soup.py
├── api/                    # FastAPI app
│   ├── __init__.py
│   ├── main.py
│   ├── routes/
│   │   ├── market.py
│   │   ├── analysts.py
│   │   ├── consensus.py
│   │   ├── scanner.py
│   │   ├── legendary.py
│   │   ├── trades.py
│   │   └── positions.py
│   └── websocket/
│       ├── __init__.py
│       └── handlers.py
├── django_app/             # Django app
│   ├── __init__.py
│   ├── settings.py
│   ├── urls.py
│   ├── models.py
│   └── admin.py
├── cache/                  # Redis cache layer
│   ├── __init__.py
│   └── redis.py
├── tasks/                  # Celery tasks
│   ├── __init__.py
│   └── analyst_tasks.py
├── config/                 # Configuration
│   ├── __init__.py
│   └── settings.py
├── requirements/
│   ├── base.txt
│   ├── dev.txt
│   └── prod.txt
└── manage.py
```

---

## Success Criteria

- [ ] All 12 analysts implement the common interface
- [ ] Each analyst returns valid AnalystResult with correct format
- [ ] Consensus engine aggregates votes and enforces 70% threshold
- [ ] Multi-timeframe scanner runs 6 timeframes in parallel
- [ ] 1H bias filter reduces confidence on misaligned shorter timeframes
- [ ] All API endpoints return correct responses
- [ ] WebSocket connections work for real-time data
- [ ] Redis caching works with correct TTLs
- [ ] Database models are properly migrated
- [ ] Unit test coverage > 80%
- [ ] Integration tests pass against test database
