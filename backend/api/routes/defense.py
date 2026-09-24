"""
Defense Status API — Defense level and circuit breaker state exposure.
"""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import asyncio
import json
from datetime import datetime, timezone, date
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
TRADING_DIR = BACKEND_DIR / "trades_complete"
STATE_FILE = TRADING_DIR / "complete_state.json"
LOG_FILE = TRADING_DIR / "complete_trades.jsonl"
DEFENSE_STATE_FILE = TRADING_DIR / "defense_state.json"


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class DefenseResponse(BaseModel):
    status: str
    reason: str
    circuit_breaker_state: str
    consecutive_losses: int
    daily_loss_pct: float
    daily_pnl: float
    total_trades_today: int
    timestamp: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _load_defense_state() -> dict:
    """Load or initialize the defense tracking state."""
    default = {
        "daily_pnl": 0.0,
        "daily_loss_pct": 0.0,
        "consecutive_losses": 0,
        "trades_today": 0,
        "last_trade_date": "",
    }

    if DEFENSE_STATE_FILE.exists():
        try:
            with open(DEFENSE_STATE_FILE, "r") as f:
                data = json.load(f)
            # Reset daily counters if it's a new day
            today = date.today().isoformat()
            if data.get("last_trade_date") != today:
                data["daily_pnl"] = 0.0
                data["daily_loss_pct"] = 0.0
                data["trades_today"] = 0
                data["last_trade_date"] = today
            return data
        except Exception:
            pass

    default["last_trade_date"] = date.today().isoformat()
    return default


def _save_defense_state(state: dict):
    TRADING_DIR.mkdir(exist_ok=True)
    with open(DEFENSE_STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def _update_defense_from_trades():
    """Scan the trade log and update defense state for today's trades."""
    defense = _load_defense_state()
    today = date.today().isoformat()

    if not LOG_FILE.exists():
        return defense

    try:
        with open(LOG_FILE, "r") as f:
            lines = f.readlines()
    except Exception:
        return defense

    consecutive = 0
    daily_pnl = 0.0
    trades_today = 0

    # Walk through trades — compute consecutive losses and today's PnL
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            trade = json.loads(line)
        except Exception:
            continue

        trade_time = trade.get("time", "")
        profit = trade.get("profit", 0)
        is_close = trade.get("action") in ("CLOSE", "close", "CLOSED") or trade.get("type") in ("close", "closed")

        # Only count closed trades for consecutive losses
        if is_close or profit != 0:
            if profit < 0:
                consecutive += 1
            elif profit > 0:
                consecutive = 0

            # Check if trade is from today
            if trade_time.startswith(today):
                daily_pnl += profit
                trades_today += 1

    # Estimate daily loss percentage from account balance
    trading_state = _load_state()
    balance = trading_state.get("balance", 10000)
    daily_loss_pct = abs(min(0, daily_pnl)) / balance * 100 if balance > 0 else 0

    defense["daily_pnl"] = daily_pnl
    defense["daily_loss_pct"] = round(daily_loss_pct, 4)
    defense["consecutive_losses"] = consecutive
    defense["trades_today"] = trades_today
    defense["last_trade_date"] = today

    _save_defense_state(defense)
    return defense


def _determine_defense_level(defense: dict) -> tuple[str, str]:
    """
    Determine defense level from daily loss and consecutive losses.
    Returns (status, reason).
    """
    daily_loss = defense.get("daily_loss_pct", 0)
    consecutive = defense.get("consecutive_losses", 0)

    # EMERGENCY: daily loss > 5% or consecutive losses > 5
    if daily_loss > 5.0 or consecutive > 5:
        reasons = []
        if daily_loss > 5.0:
            reasons.append(f"daily loss {daily_loss:.1f}% > 5%")
        if consecutive > 5:
            reasons.append(f"consecutive losses {consecutive} > 5")
        return "EMERGENCY", "; ".join(reasons)

    # DEFENSE: daily loss > 3% or consecutive losses > 3
    if daily_loss > 3.0 or consecutive > 3:
        reasons = []
        if daily_loss > 3.0:
            reasons.append(f"daily loss {daily_loss:.1f}% > 3%")
        if consecutive > 3:
            reasons.append(f"consecutive losses {consecutive} > 3")
        return "DEFENSE", "; ".join(reasons)

    # CAUTION: daily loss > 1% or consecutive losses > 2
    if daily_loss > 1.0 or consecutive > 2:
        reasons = []
        if daily_loss > 1.0:
            reasons.append(f"daily loss {daily_loss:.1f}% > 1%")
        if consecutive > 2:
            reasons.append(f"consecutive losses {consecutive} > 2")
        return "CAUTION", "; ".join(reasons)

    return "NORMAL", "All risk parameters within limits"


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

@router.get("/status")
async def get_defense_status():
    """Return defense status and circuit breaker state."""
    def _work():
        defense = _update_defense_from_trades()
        status, reason = _determine_defense_level(defense)

        # Map circuit breaker: use file state if available, else infer from status
        circuit_state = "CLOSED"
        cb_file = TRADING_DIR / "trading_control.json"
        if cb_file.exists():
            try:
                with open(cb_file, "r") as f:
                    cb_data = json.load(f)
                control_status = cb_data.get("status", "running")
                if control_status == "stopped":
                    circuit_state = "OPEN"
            except Exception:
                pass

        # If defense is EMERGENCY, force circuit to OPEN
        if status == "EMERGENCY":
            circuit_state = "OPEN"
        elif status == "DEFENSE":
            circuit_state = "HALF_OPEN" if circuit_state == "CLOSED" else circuit_state
        elif status == "CAUTION":
            circuit_state = "HALF_OPEN" if circuit_state == "CLOSED" else circuit_state

        return DefenseResponse(
            status=status,
            reason=reason,
            circuit_breaker_state=circuit_state,
            consecutive_losses=defense.get("consecutive_losses", 0),
            daily_loss_pct=defense.get("daily_loss_pct", 0.0),
            daily_pnl=defense.get("daily_pnl", 0.0),
            total_trades_today=defense.get("trades_today", 0),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
    return await asyncio.to_thread(_work)
