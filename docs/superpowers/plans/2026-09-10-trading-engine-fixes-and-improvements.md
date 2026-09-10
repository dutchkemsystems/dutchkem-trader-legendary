# Trading Engine Fixes & Profit Optimization Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the trading engine so it actually executes trades, then optimize for higher profits and better risk management.

**Architecture:** Fix pipe deadlock → Add watchdog → Relax filters → Add profit-taking → Add risk controls → Add smarter signals.

**Tech Stack:** Python 3.11+, MetaTrader5, pandas, numpy, subprocess, threading

---

## Task 1: Fix Pipe Deadlock + Add Log File

**Files:**
- Modify: `backend/api/routes/live_trading.py:335-373`

**What to do:**
- Step 1: Replace `stdout=subprocess.PIPE` with a log file to prevent deadlock
- Step 2: Add stderr redirect to same log file
- Step 3: Verify fix

**Must NOT do:**
- Do not change the engine script itself

**Verify:**
- [ ] Run: `python -c "import subprocess; print('OK')"` → passes

---

## Task 2: Add Process Watchdog

**Files:**
- Modify: `backend/api/routes/live_trading.py:335-400`
- Create: `backend/api/routes/trading_watchdog.py`

**What to do:**
- Step 1: Create watchdog thread that checks if engine process is alive
- Step 2: Auto-restart if process dies unexpectedly
- Step 3: Update control file when process dies

---

## Task 3: Validate Control File via PID Check

**Files:**
- Modify: `backend/api/routes/live_trading.py:285-304, 483-497`

**What to do:**
- Step 1: Update `read_control()` to check if PID is alive
- Step 2: Update `/status` endpoint to verify engine is actually running
- Step 3: Return accurate status to dashboard

---

## Task 4: Remove MT5 Connection Interference

**Files:**
- Modify: `backend/api/routes/live_trading.py:113-157`

**What to do:**
- Step 1: Check if engine is running before calling `mt5.initialize()` in `detect_mt5()`
- Step 2: Use `tasklist` check only when engine is running
- Step 3: Prevent API from killing engine's MT5 connection

---

## Task 5: Relax Signal Filters

**Files:**
- Modify: `backend/live_trading_complete.py:91-150` (CONFIG)
- Modify: `backend/live_trading_complete.py:363-455` (generate_signal_single_tf)
- Modify: `backend/live_trading_complete.py:461-532` (analyze_symbol_mtf)

**What to do:**
- Step 1: Lower `adx_threshold` from 30 to 20
- Step 2: Reduce `min_timeframes_agree` from 3 to 2
- Step 3: Make D1/H4 agreement a soft filter (bonus points, not hard block)
- Step 4: Add session volatility filter (prefer London/NY overlap)

---

## Task 6: Add Partial Take-Profit

**Files:**
- Modify: `backend/live_trading_complete.py:765-829` (close_position)
- Modify: `backend/live_trading_complete.py:831-871` (check_trailing_stop)

**What to do:**
- Step 1: Close 50% of position at 1:1 R:R
- Step 2: Trail the remaining 50% with ATR-based trailing stop
- Step 3: Lock in profits while letting winners run

---

## Task 7: Add Portfolio Heat Limit

**Files:**
- Modify: `backend/live_trading_complete.py:672-763` (open_position)
- Modify: `backend/live_trading_complete.py:91-150` (CONFIG)

**What to do:**
- Step 1: Add `max_concurrent_trades` config (default: 3)
- Step 2: Check open positions before opening new ones
- Step 3: Prevent over-concentration in correlated assets

---

## Task 8: Dynamic Position Sizing by Equity Curve

**Files:**
- Modify: `backend/live_trading_complete.py:642-670` (get_lot_size)
- Modify: `backend/live_trading_complete.py:91-150` (CONFIG)

**What to do:**
- Step 1: Scale position size with equity curve (compound growth)
- Step 2: Reduce size during drawdown
- Step 3: Increase size during winning streaks

---

## Task 9: Drawdown-Based Throttle

**Files:**
- Modify: `backend/live_trading_complete.py:550-559` (get_dynamic_risk)
- Modify: `backend/live_trading_complete.py:91-150` (CONFIG)

**What to do:**
- Step 1: Add drawdown tracking (peak equity vs current)
- Step 2: Reduce risk by 50% after -5% drawdown
- Step 3: Reduce risk by 75% after -10% drawdown
- Step 4: Pause trading after -15% drawdown

---

## Task 10: Session Volatility Filter

**Files:**
- Modify: `backend/live_trading_complete.py:911-931` (run_cycle)
- Modify: `backend/live_trading_complete.py:91-150` (CONFIG)

**What to do:**
- Step 1: Define optimal trading sessions (London/NY overlap: 13:00-17:00 UTC)
- Step 2: Reduce position size during low-volatility sessions
- Step 3: Skip trading during Asian session (low liquidity for forex)

---

## Task 11: Multi-Timeframe Momentum Weighting

**Files:**
- Modify: `backend/live_trading_complete.py:461-532` (analyze_symbol_mtf)

**What to do:**
- Step 1: Weight signals by timeframe (D1 > H4 > H1 > M30 > M15 > M10 > M5)
- Step 2: Require higher-timeframe confirmation for entry
- Step 3: Reduce false signals from lower timeframes

---

## Task 12: Volume Confirmation Enhancement

**Files:**
- Modify: `backend/live_trading_complete.py:363-455` (generate_signal_single_tf)

**What to do:**
- Step 1: Require above-average volume for entry信号
- Step 2: Increase confidence when volume is 2x+ average
- Step 3: Reduce confidence when volume is below average

---

## Task 13: Volatility Regime Detection

**Files:**
- Modify: `backend/live_trading_complete.py:316-360` (compute_indicators)
- Modify: `backend/live_trading_complete.py:91-150` (CONFIG)

**What to do:**
- Step 1: Calculate ATR percentile (high/medium/low volatility)
- Step 2: Adjust SL/TP based on volatility regime
- Step 3: Reduce position size in high-volatility environments

---

## Task 14: Mean Reversion at Extremes

**Files:**
- Modify: `backend/live_trading_complete.py:363-455` (generate_signal_single_tf)
- Modify: `backend/live_trading_complete.py:91-150` (CONFIG)

**What to do:**
- Step 1: Detect RSI extremes (<30 or >70) at support/resistance
- Step 2: Generate counter-trend signals with smaller position size
- Step 3: Use tighter SL for mean reversion trades

---

## Task 15: News Calendar Integration (Placeholder)

**Files:**
- Modify: `backend/live_trading_complete.py:579-586` (check_news_filter)

**What to do:**
- Step 1: Add economic calendar API integration (placeholder)
- Step 2: Skip trades 30min before high-impact news
- Step 3: Reduce position size during news events

---

## Task 16: Final Integration Test

**Files:**
- Create: `backend/tests/test_trading_engine_improvements.py`

**What to do:**
- Step 1: Test all new filters work together
- Step 2: Verify partial take-profit logic
- Step 3: Verify portfolio heat limit
- Step 4: Verify drawdown throttle
- Step 5: Run full integration test

---

## Success Criteria

- [ ] Engine process stays alive (no pipe deadlock)
- [ ] Process watchdog auto-restarts if engine dies
- [ ] Control file accurately reflects engine status
- [ ] MT5 connection not interfered with by API
- [ ] More trades executed (relaxed filters)
- [ ] Partial take-profit locks in profits
- [ ] Portfolio heat limit prevents over-concentration
- [ ] Dynamic position sizing scales with equity
- [ ] Drawdown throttle protects capital
- [ ] Session filter trades during optimal hours
- [ ] All tests passing
