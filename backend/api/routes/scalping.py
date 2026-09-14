"""Scalping strategies API routes."""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any

router = APIRouter()


@router.get("/scalping/status")
async def get_scalping_status():
    """Get status of all scalping strategies."""
    from apps.scalping.config import SCALPING_STRATEGIES
    return {
        "strategies": [
            {
                "name": name,
                "enabled": config.get("enabled", False),
                "trades": 0,
                "winRate": 0,
                "pnl": 0,
                "status": "disabled"
            }
            for name, config in SCALPING_STRATEGIES.items()
        ],
        "active_trades": [],
        "total_pnl": 0.0
    }


@router.post("/scalping/toggle/{strategy_name}")
async def toggle_strategy(strategy_name: str, body: Dict[str, bool]):
    """Toggle a strategy on/off."""
    from apps.scalping.config import SCALPING_STRATEGIES
    if strategy_name not in SCALPING_STRATEGIES:
        raise HTTPException(status_code=404, detail=f"Strategy {strategy_name} not found")
    SCALPING_STRATEGIES[strategy_name]['enabled'] = body.get('enabled', False)
    return {
        "status": "ok",
        "strategy": strategy_name,
        "enabled": SCALPING_STRATEGIES[strategy_name]['enabled']
    }
