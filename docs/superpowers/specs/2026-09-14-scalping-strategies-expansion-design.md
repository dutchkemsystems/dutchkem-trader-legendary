# Scalping Strategies Expansion — Design Spec

**Date:** 2026-09-14
**Feature:** scalping-strategies-expansion
**Status:** APPROVED

---

## 1. Original Request

Add 10 new scalping strategies to the D-T Ventures trading system. Each strategy focuses on extracting 10–20 pips from the market at the earliest opportunity, with strict risk management.

## 2. Interview Summary

**User decisions:**
- **Implementation scope:** Full 10 strategies (no removals)
- **Integration mode:** Parallel (both engines run simultaneously)
- **First strategy:** Chiaroscuro (strategy #2), then London/NY Overlap (strategy #1)
- **Conflict resolution:** Allow both main engine and scalping to trade same symbol
- **Magic numbers:** 234010-234019 range
- **Dashboard:** Full Next.js panel from day 1
- **Testing:** Full test suite (unit + integration + backtest + paper trade)
- **Batch size:** 3 strategies per batch, 4 batches total

## 3. Research Findings

### Current Architecture
- **Monolithic engine:** `unified_engine.py` (5524 lines) contains everything
- **RiskManager:** Already robust (circuit breaker, daily limits, correlation, position sizing)
- **MTF Cascading Scalper:** Exists at `backend/apps/legendary/mtf_cascading_scalper.py` (703 lines)
- **Feature flags:** Simple boolean toggles in CONFIG dict (no formal system)
- **Dashboard:** Next.js with existing `ScalperDashboardPanel`
- **MT5 execution:** Two layers — direct (`MT5Client`) and broker abstraction

### Key Integration Points
- `UnifiedEngine.run()` — main trading loop (every 5 minutes)
- `RiskManager` — gatekeeper for all trades
- `MT5Client.place_order()` — execution with magic numbers
- `CONFIG` dict — feature flags and parameters

## 4. Non-Goals

- **NOT refactoring** the monolithic `unified_engine.py` (out of scope)
- **NOT modifying** existing strategies (Legendary, MTF Scalper)
- **NOT changing** the RiskManager (strategies only place orders; RiskManager approves)
- **NOT implementing** automated backtesting UI (backtests run via scripts)
- **NOT removing** any existing features

## 5. Architecture

### Module Structure
```
backend/apps/scalping/
├── __init__.py
├── base.py              # ScalpingStrategy base class + ScalpSignal
├── engine.py            # ScalpingEngine (parallel runner)
├── config.py            # All strategy configurations
├── risk.py              # Scalping-specific risk extensions
├── signals.py           # Signal dataclass
├── indicators/          # Shared indicator calculations
│   ├── __init__.py
│   ├── order_blocks.py  # Chiaroscuro
│   ├── fvg.py           # Fair Value Gap
│   ├── renko.py         # Renko charts
│   └── supply_demand.py # Sniper
├── strategies/
│   ├── __init__.py
│   ├── chiaroscuro.py   # Strategy 2
│   ├── london_ny.py     # Strategy 1
│   ├── checklist_5pt.py # Strategy 3
│   ├── autolot.py       # Strategy 4
│   ├── renko.py         # Strategy 5
│   ├── sniper.py        # Strategy 6
│   ├── ema_pullback.py  # Strategy 7
│   ├── session_breakout.py # Strategy 8
│   ├── news_fade.py     # Strategy 9
│   └── fvg_confluence.py # Strategy 10
└── tests/
    ├── test_base.py
    ├── test_engine.py
    └── test_[strategy].py (10 files)
```

### Integration with Main Engine
```python
# In unified_engine.py UnifiedEngine.run() — AFTER existing trading loop:
async def _run_scalping_strategies(self):
    if not hasattr(self, 'scalping_engine'):
        from apps.scalping.engine import ScalpingEngine
        self.scalping_engine = ScalpingEngine(self.mt5_client, self.risk_manager)
    if self.scalping_engine.strategies:
        await self.scalping_engine.run_cycle(self.WATCHLIST)
```

### Data Flow
```
Symbol Loop (every 5 min)
  │
  ├─→ [Main Engine] — existing pipeline (indicators → consensus → gates → execute)
  │
  └─→ [Scalping Engine] — NEW parallel pipeline:
        │
        ├─→ Check session filter (London/NY only)
        ├─→ Check daily loss limit
        │
        └─→ For each enabled strategy:
              ├─→ Fetch M1/M5/M15/H1 data
              ├─→ strategy.analyze(symbol, data)
              ├─→ Validate signal
              ├─→ RiskManager checks (spread, correlation, limits)
              └─→ MT5Client.place_order(magic=234010+index)
```

## 6. The 10 Strategies

### Strategy 1: London/NY Overlap Scalping
- **Timeframes:** M1, M5
- **Logic:** During 13:00-17:00 GMT, detect tight-range consolidation (BB squeeze), enter on breakout with volume confirmation
- **TP:** 15 pips, **SL:** 10 pips

### Strategy 2: Chiaroscuro Scalp Model
- **Timeframes:** M5, M15, H1
- **Logic:** Daily range expansion + order blocks + FVGs during London/NY sessions
- **TP:** 20 pips, **SL:** 12 pips

### Strategy 3: 5-Point Checklist
- **Timeframes:** M5, H1
- **Logic:** ALL 5 conditions: H1 impulse, premium/discount zone, POI, liquidity sweep, session window
- **TP:** 15 pips, **SL:** 10 pips

### Strategy 4: AutoLot 20-Pip EA
- **Timeframes:** M5
- **Logic:** EMA(10) crosses EMA(20) + RSI momentum + ADX >25 + H1 trend alignment
- **TP:** 20 pips, **SL:** 20 pips

### Strategy 5: Renko 20-Pip System
- **Timeframes:** Renko (10-pip bricks, offline M3)
- **Logic:** Renko noise filter + oscillator + trendline + BB_stop alignment
- **TP:** 20 pips, **SL:** 20 pips

### Strategy 6: Sniper
- **Timeframes:** M1, M5
- **Logic:** Supply/demand zones + price action rejection candles at institutional levels
- **TP:** 15 pips, **SL:** 10 pips

### Strategy 7: 10/20 EMA Pullback
- **Timeframes:** M5
- **Logic:** 10 EMA crosses 20 EMA, enter on pullback with confirmation candle
- **TP:** 20 pips, **SL:** 12 pips

### Strategy 8: Session Open Breakout
- **Timeframes:** M5, M15
- **Logic:** Trade first 30-60 min of London/NY. Breakout of Asian range.
- **TP:** 15 pips, **SL:** 10 pips

### Strategy 9: News Spike Fade
- **Timeframes:** M1, M5
- **Logic:** After high-impact news, wait for spike exhaustion, enter counter-trend
- **TP:** 12 pips, **SL:** 8 pips

### Strategy 10: Multi-Timeframe FVG Confluence
- **Timeframes:** M5, H4
- **Logic:** H4 FVGs as reference, enter on M5 when price returns with confirmation
- **TP:** 15 pips, **SL:** 10 pips

## 7. Risk Management

All strategies enforce:
- **Daily Loss Limit:** 2% — Stop trading for the day
- **Risk Per Trade:** 0.5% — Position size based on stop distance
- **Minimum R:R:** 1:1.5
- **Stop After 3 Consecutive Losses:** Pause for session
- **Spread Filter:** Skip if spread > 1.5 pips
- **Session Filter:** Only London/NY hours
- **Correlation Filter:** Max 2 correlated pairs
- **Max Concurrent Scalps:** 4

All enforced by existing `RiskManager` — strategies only place orders.

## 8. Feature Flags

```python
# Added to unified_engine.py CONFIG dict
"scalping_engine_enabled": True,      # Master switch
"scalp_chiaroscuro": False,
"scalp_london_ny_overlap": False,
"scalp_5point_checklist": False,
"scalp_autolot_20pip": False,
"scalp_renko_20pip": False,
"scalp_sniper": False,
"scalp_ema_pullback": False,
"scalp_session_breakout": False,
"scalp_news_fade": False,
"scalp_fvg_confluence": False,
```

## 9. Dashboard

New Next.js component: `ScalpingStrategiesPanel`
- Strategy status with ON/OFF toggles
- Active trades table with P&L
- Per-strategy performance metrics
- Cumulative P&L chart

## 10. Testing

| Type | Scope | Tool |
|------|-------|------|
| Unit | Each strategy's analyze() | pytest + mock data |
| Integration | Signal → RiskManager → MT5 | pytest + simulated broker |
| Backtest | 1-year historical data | Custom backtest harness |
| Paper Trade | 1 week per strategy | Live MT5 demo account |

Success criteria: PF > 1.3, Sharpe > 1.0, DD < 15%

## 11. Implementation Batches

| Batch | Strategies | Est. Lines |
|-------|-----------|------------|
| 1 | Chiaroscuro, London/NY Overlap, Session Breakout | ~800 |
| 2 | Sniper, FVG Confluence, 5-Point Checklist | ~700 |
| 3 | AutoLot, EMA Pullback, Renko | ~600 |
| 4 | News Fade + Dashboard + API + Backtests | ~500 |

## 12. Deliverables

- `backend/apps/scalping/` — Base class + 10 strategies
- Updated `unified_engine.py` — Feature flags + integration hook
- `frontend/components/dashboard/scalping-strategies-panel.tsx` — Dashboard
- `backend/api/routes/scalping.py` — API endpoints
- `backend/apps/scalping/tests/` — Unit + integration tests
- Backtest reports per strategy
