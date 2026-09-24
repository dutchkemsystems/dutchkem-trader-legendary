"""Scalping strategies API routes.

Toggle state is persisted to a shared JSON file so the engine subprocess
(live_trading_complete.py) can read it even though it runs in a separate process.
"""

import json
from pathlib import Path
from fastapi import APIRouter, HTTPException
from typing import Dict, Any

router = APIRouter()

# Shared state file — both API and engine subprocess read/write this
TOGGLE_STATE_FILE = Path(__file__).resolve().parent.parent.parent / "trades_complete" / "toggle_state.json"

# In-memory cache for toggle state (avoids repeated disk reads per request)
_toggle_cache: dict = {}
_toggle_cache_ts: float = 0

ENGINE_TOGGLE_MAP = {
    "main_engine": "main_engine_enabled",
    "mtf_scalper": "mtf_cascading_scalper_enabled",
}


def _load_toggle_state() -> dict:
    """Load toggle state from shared file, cached for 2s to avoid repeated disk reads."""
    import time as _time
    global _toggle_cache, _toggle_cache_ts
    now = _time.time()
    if _toggle_cache and (now - _toggle_cache_ts) < 2.0:
        return _toggle_cache
    if TOGGLE_STATE_FILE.exists():
        try:
            _toggle_cache = json.loads(TOGGLE_STATE_FILE.read_text(encoding="utf-8"))
            _toggle_cache_ts = now
            return _toggle_cache
        except Exception:
            pass
    return {}


def _save_toggle_state(state: dict):
    """Save toggle state to shared file."""
    TOGGLE_STATE_FILE.parent.mkdir(exist_ok=True)
    TOGGLE_STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _get_toggle(name: str, default: bool = True) -> bool:
    """Get a toggle value, falling back to unified_engine.CONFIG."""
    state = _load_toggle_state()
    if name in state:
        return state[name]
    # Fallback to unified_engine CONFIG
    try:
        from unified_engine import CONFIG
        return CONFIG.get(f"{name}_enabled" if not name.endswith("_enabled") else name, default)
    except Exception:
        return default


def _set_toggle(name: str, enabled: bool):
    """Set a toggle in both shared file and unified_engine.CONFIG."""
    state = _load_toggle_state()
    state[name] = enabled
    _save_toggle_state(state)
    # Also update unified_engine CONFIG in-process
    try:
        from unified_engine import CONFIG
        CONFIG[name] = enabled
    except Exception:
        pass


# Also set scalping strategy toggles in shared state
SCALPING_TOGGLE_KEY = "scalping_strategies"


def _get_strategy_toggle(name: str) -> bool:
    """Get a scalping strategy toggle."""
    state = _load_toggle_state()
    strats = state.get(SCALPING_TOGGLE_KEY, {})
    if name in strats:
        return strats[name]
    # Fallback to config
    try:
        from apps.scalping.config import SCALPING_STRATEGIES
        return SCALPING_STRATEGIES.get(name, {}).get("enabled", False)
    except Exception:
        return False


def _set_strategy_toggle(name: str, enabled: bool):
    """Set a scalping strategy toggle in both shared file and config."""
    state = _load_toggle_state()
    if SCALPING_TOGGLE_KEY not in state:
        state[SCALPING_TOGGLE_KEY] = {}
    state[SCALPING_TOGGLE_KEY][name] = enabled
    _save_toggle_state(state)
    # Also update in-process config
    try:
        from apps.scalping.config import SCALPING_STRATEGIES
        if name in SCALPING_STRATEGIES:
            SCALPING_STRATEGIES[name]["enabled"] = enabled
    except Exception:
        pass


# ── Endpoints ──

@router.get("/status")
async def get_scalping_status():
    """Get status of all scalping strategies and engine toggles."""
    from apps.scalping.config import SCALPING_STRATEGIES

    strategies = [
        {
            "name": name,
            "enabled": _get_strategy_toggle(name),
            "trades": 0,
            "winRate": 0,
            "pnl": 0,
            "status": "active" if _get_strategy_toggle(name) else "disabled"
        }
        for name in SCALPING_STRATEGIES
    ]

    engine_toggles = {
        toggle_name: _get_toggle(config_key, default=(toggle_name == "main_engine"))
        for toggle_name, config_key in ENGINE_TOGGLE_MAP.items()
    }

    return {
        "engine_toggles": engine_toggles,
        "strategies": strategies,
        "active_trades": [],
        "total_pnl": 0.0
    }


@router.get("/gold-hedge")
async def get_gold_hedge_status():
    """Get Gold Hedge EA status."""
    from apps.scalping.config import SCALPING_STRATEGIES
    gold_config = SCALPING_STRATEGIES.get("gold_hedge_ea", {})
    return {
        "active": _get_strategy_toggle("gold_hedge_ea"),
        "enabled": _get_strategy_toggle("gold_hedge_ea"),
        "symbol": gold_config.get("symbol", "XAUUSD"),
        "levels": 0,
        "total_lots": 0,
        "pnl": 0,
    }


@router.post("/toggle/{strategy_name}")
async def toggle_strategy(strategy_name: str, body: Dict[str, bool]):
    """Toggle a scalping strategy on/off."""
    from apps.scalping.config import SCALPING_STRATEGIES
    if strategy_name not in SCALPING_STRATEGIES:
        raise HTTPException(status_code=404, detail=f"Strategy {strategy_name} not found")
    enabled = body.get("enabled", False)
    _set_strategy_toggle(strategy_name, enabled)
    return {
        "status": "ok",
        "strategy": strategy_name,
        "enabled": enabled
    }


@router.get("/engine-toggle")
async def get_engine_toggles():
    """Get status of engine master toggles."""
    return {
        toggle_name: _get_toggle(config_key, default=(toggle_name == "main_engine"))
        for toggle_name, config_key in ENGINE_TOGGLE_MAP.items()
    }


@router.post("/engine-toggle/{toggle_name}")
async def toggle_engine(toggle_name: str, body: Dict[str, bool]):
    """Toggle engine components on/off (main_engine, mtf_scalper).
    
    Writes to shared state file so the engine subprocess picks up the change.
    """
    if toggle_name not in ENGINE_TOGGLE_MAP:
        raise HTTPException(
            status_code=404,
            detail=f"Toggle '{toggle_name}' not found. Available: {list(ENGINE_TOGGLE_MAP.keys())}"
        )
    config_key = ENGINE_TOGGLE_MAP[toggle_name]
    enabled = body.get("enabled", False)
    _set_toggle(config_key, enabled)
    return {
        "status": "ok",
        "toggle": toggle_name,
        "config_key": config_key,
        "enabled": enabled,
        "note": "Toggle saved to shared state file. Engine picks up on next cycle."
    }
