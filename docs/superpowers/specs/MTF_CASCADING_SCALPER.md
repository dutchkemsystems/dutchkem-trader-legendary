# MTF Cascading Scalper ΓÇö Strategy Spec

**Date:** 2026-09-11
**Status:** Approved
**Feature:** mtf-cascading-scalper (Tasks 1ΓÇô11)

---

## Overview

A synchronous multi-timeframe cascading scalping strategy that scans groups of 3 timeframes for directional alignment and executes scalp trades when all 3 timeframes agree on direction. The strategy runs inside the UnifiedEngine trading loop and integrates with the existing RiskManager for safety checks.

**Key design principle:** The scalper is fully synchronous (no LLM, no async) to avoid conflicts with the engine's synchronous `run_cycle()` loop. Signal computation uses RSI, SMA20/50, and MACD ΓÇö fast enough for real-time scanning.

---

## Strategy Logic

### Signal Computation (per timeframe)

Each timeframe's OHLCV data is analyzed using a 4-point scoring system:

| Condition | Bull Points | Bear Points |
|-----------|-------------|-------------|
| RSI < 70 (not overbought) | +1 | ΓÇö |
| Close > SMA20 | +1 | ΓÇö |
| SMA20 > SMA50 | +1 | ΓÇö |
| MACD > 0 | +1 | ΓÇö |

**Decision:**
- **BUY** ΓÇö bull_score >= 3 (strong bullish alignment)
- **SELL** ΓÇö bull_score <= 1 (strong bearish alignment)
- **HOLD** ΓÇö bull_score == 2 (mixed signals, no trade)

### Cascading Group Alignment

The scalper organizes timeframes into 7 overlapping groups. Each group contains 3 timeframes at increasing granularity:

| Group | Timeframes | Entry TF | Purpose |
|-------|------------|----------|---------|
| 1 | M1, M5, M15 | M1 | Ultra-short scalps |
| 2 | M5, M15, M30 | M5 | Short-term scalps |
| 3 | M15, M30, H1 | M15 | Intraday scalps |
| 4 | M30, H1, H4 | M30 | Intraday swings |
| 5 | H1, H4, D1 | H1 | Medium-term scalps |
| 6 | H4, D1, W1 | H4 | Swing scalps |
| 7 | D1, W1, MN1 | D1 | Position scalps |

**Alignment rule:** All 3 timeframes in a group must return the same signal (BUY or SELL). If any timeframe returns HOLD or a different direction, no trade is executed for that group.

### Scan Order

- By default (`scalper_restart_from_group1=True`), only Group 1 is scanned per cycle.
- After a trade is executed (or Group 1 has no alignment), scanning restarts from Group 1 on the next cycle.
- This ensures the most aggressive (shortest) timeframe group gets priority.

---

## Configuration Parameters

All parameters are defined in the `CONFIG` dict in `backend/unified_engine.py`:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `mtf_cascading_scalper_enabled` | bool | `False` | Master enable/disable switch |
| `scalper_timeframes` | list[str] | `["M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1", "MN1"]` | Available timeframes for groups |
| `scalper_groups` | list[list[str]] | 7 groups (see above) | Timeframe triplets for alignment |
| `scalper_tp_pips` | int | `10` | Take-profit in pips |
| `scalper_sl_pips` | int | `5` | Stop-loss in pips |
| `scalper_lot_size` | float | `0.01` | Fixed lot size per trade |
| `scalper_max_concurrent` | int | `3` | Max simultaneous open scalper trades |
| `scalper_scan_interval` | int | `60` | Seconds between scan cycles |
| `scalper_restart_from_group1` | bool | `True` | Restart scan from Group 1 each cycle |
| `scalper_symbol` | str | `"EURUSD"` | Symbol to scalp |

### Risk:Reward Ratio

With defaults (TP=10 pips, SL=5 pips), the R:R ratio is **2:1** ΓÇö each winning trade gains twice what a losing trade loses.

---

## How to Enable/Disable

1. Open `backend/unified_engine.py`
2. Find the `CONFIG` dict (line ~144)
3. Set `mtf_cascading_scalper_enabled` to `True`:

```python
CONFIG = {
    ...
    "mtf_cascading_scalper_enabled": True,  # Enable scalper
    ...
}
```

4. Restart the engine:
```bash
cd backend
python unified_engine.py
```

**To disable:** Set the flag back to `False` and restart. The scalper will not initialize and will not appear in engine status.

### API Toggle (Runtime)

While the engine is running, the scalper status is available at:

```
GET /api/v1/scalper/status
```

Returns:
```json
{
  "enabled": true,
  "open_scalps": 0,
  "total_trades": 5,
  "last_scan": "2026-09-11T14:30:00+00:00",
  "last_error": null,
  "symbol": "EURUSD",
  "tp_pips": 10,
  "sl_pips": 5,
  "max_concurrent": 3,
  "groups": ["Group 1", "Group 2", "Group 3", "Group 4", "Group 5", "Group 6", "Group 7"]
}
```

---

## Engine Integration

### Trading Loop Position

The scalper runs inside `UnifiedEngine.run_cycle()` at a specific position:

```
run_cycle():
  1. Account state update
  2. Position management (TP/SL/trailing)
  3. [SCALPER] scan_and_execute() + refresh_trade_statuses()
  4. Main symbol scan (12 analysts + consensus)
  5. Trade execution
```

The scalper runs **after** position management but **before** the main analyst scan, ensuring it doesn't interfere with existing trade logic.

### Initialization

In `UnifiedEngine.__init__()`:
```python
if CONFIG.get("mtf_cascading_scalper_enabled"):
    from apps.legendary.mtf_cascading_scalper import MTFCascadingScalper
    self.scalper = MTFCascadingScalper(self.mt5, self.risk, CONFIG)
else:
    self.scalper = None
```

The scalper receives references to:
- `mt5` ΓÇö MT5Client for market data and order execution
- `risk` ΓÇö RiskManager for drawdown, circuit breaker, and portfolio limit checks
- `CONFIG` ΓÇö Full configuration dict

---

## Safety Checks

Before every scan, the scalper runs 5 safety checks:

| Check | Condition | Action if Failed |
|-------|-----------|------------------|
| Session filter | Current UTC hour in `session_hours` (7ΓÇô21) | Skip scan |
| Drawdown pause | `risk_manager.get_drawdown_pct()` < `drawdown_pause_pct` (15%) | Skip scan |
| Circuit breaker | `risk_manager.check_circuit_breaker()` passes | Skip scan |
| Max concurrent | Open scalps < `scalper_max_concurrent` (3) | Skip scan |
| Portfolio limits | `risk_manager.check_portfolio_limits()` passes | Skip scan |

All checks must pass for the scalper to proceed with signal scanning.

---

## Dashboard Panel

The scalper status is displayed on the main dashboard via `ScalperDashboardPanel`:

- **Current group** being scanned (visual indicator)
- **Alignment status** for each group (green = aligned, grey = not aligned)
- **Active trades** table (direction, entry price, group, P&L)
- **Cumulative profit** and **win rate**
- **Enable/disable** indicator

The panel polls `GET /api/v1/scalper/status` every 10 seconds via the `useScalper()` hook.

---

## Risk Considerations

### Position Sizing

- Fixed lot size (default 0.01) ΓÇö not equity-based
- Max 3 concurrent scalper trades
- Scalper trades use the existing RiskManager for portfolio-level limits

### R:R Asymmetry

- Default R:R is 2:1 (TP=10 pips, SL=5 pips)
- Requires >33% win rate to be profitable
- Tight SL means more frequent stops ΓÇö higher win rate needed

### Drawdown Protection

- 15% drawdown pause (shared with main engine)
- Circuit breaker (3 consecutive losses ΓåÆ 60-min cooldown)
- Session filter (no trading outside 07:00ΓÇô21:00 UTC)

### Symbol Risk

- Default: EURUSD only (`scalper_symbol`)
- Can be changed to any MT5-available symbol
- JPY pairs require different pip calculations (handled automatically via `symbol_info.point`)

### Correlation

- Scalper trades are independent of main engine trades
- RiskManager enforces max 2 correlated pairs across all strategies
- Consider reducing `scalper_max_concurrent` if running alongside main engine

---

## Backtesting Recommendations

### Parameters to Test

| Parameter | Range | Notes |
|-----------|-------|-------|
| `scalper_tp_pips` | 5ΓÇô20 | Tighter = more trades, wider = fewer but larger |
| `scalper_sl_pips` | 3ΓÇô10 | Must be < TP for positive R:R |
| `scalper_groups` | 1ΓÇô7 groups | Fewer groups = less frequent trading |
| `scalper_symbol` | Major FX pairs | EURUSD, GBPUSD, USDJPY |

### Recommended Approach

1. **Start with defaults** ΓÇö TP=10, SL=5, Group 1 only
2. **Run on M1 data** ΓÇö 100+ bars per signal computation
3. **Test across sessions** ΓÇö London, NY, overlap, off-hours
4. **Monitor win rate** ΓÇö Target >40% for profitability with 2:R R:R
5. **Check drawdown** ΓÇö Ensure max DD stays below 15%

### Limitations

- No trailing stop (TP is the primary exit)
- No partial take-profit (full exit at TP)
- Fixed lot size (not Kelly-sized)
- Single symbol (no multi-symbol diversification within scalper)

---

## File Structure

```
backend/
Γö£ΓöÇΓöÇ apps/legendary/
Γöé   ΓööΓöÇΓöÇ mtf_cascading_scalper.py    # Core scalper module
Γö£ΓöÇΓöÇ unified_engine.py                # Config + engine integration
ΓööΓöÇΓöÇ tests/
    Γö£ΓöÇΓöÇ unit/
    Γöé   ΓööΓöÇΓöÇ test_mtf_cascading_scalper.py    # 17 unit tests
    ΓööΓöÇΓöÇ integration/
        ΓööΓöÇΓöÇ test_scalper_integration.py       # 20 integration tests

frontend/
Γö£ΓöÇΓöÇ components/dashboard/
Γöé   ΓööΓöÇΓöÇ scalper-dashboard-panel.tsx   # Dashboard panel
Γö£ΓöÇΓöÇ hooks/
Γöé   ΓööΓöÇΓöÇ use-scalper.ts               # Polling hook
Γö£ΓöÇΓöÇ lib/
Γöé   Γö£ΓöÇΓöÇ types-v5.ts                   # ScalperStatus type
Γöé   ΓööΓöÇΓöÇ api.ts                        # getScalperStatus()
ΓööΓöÇΓöÇ app/dashboard/
    ΓööΓöÇΓöÇ page.tsx                       # Panel integrated
```

---

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/scalper/status` | GET | Scalper status and stats |
| `/api/v1/engine/status` | GET | Engine status (includes `scalper` key) |

---

## Test Coverage

| Test Type | Count | Coverage |
|-----------|-------|----------|
| Unit tests | 17 | Alignment logic, SL/TP calculation, pip values, safety checks, status structure |
| Integration tests | 20 | Engine init, API endpoint, trade execution flow, risk manager integration |
| **Total** | **37** | Full scalper functionality |

### Running Tests

```bash
# Unit tests
cd backend && python -m pytest tests/unit/test_mtf_cascading_scalper.py -v

# Integration tests
cd backend && python -m pytest tests/integration/test_scalper_integration.py -v

# All tests
cd backend && python -m pytest tests/unit/test_mtf_cascading_scalper.py tests/integration/test_scalper_integration.py -v
```

---

## Non-Goals

- **NOT** implementing trailing stops for scalper trades
- **NOT** creating a separate backtest framework
- **NOT** using async/LLM for signal computation
- **NOT** modifying existing analyst or legendary agent code
- **NOT** adding new MT5 dependencies or changing broker connection logic
