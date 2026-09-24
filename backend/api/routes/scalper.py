"""MTF Cascading Scalper API routes.

Provides /scalper/status for the frontend ScalperDashboardPanel.
"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/status")
async def get_scalper_status():
    """Get MTF Cascading Scalper status for the dashboard.

    The frontend useScalper() hook polls this every 10s.
    Returns data matching the ScalperStatus type in types-v5.ts.
    """
    # Try to get from running engine
    try:
        from unified_engine import engine as _engine
        if _engine and hasattr(_engine, "scalper") and _engine.scalper:
            raw = _engine.scalper.get_status()
            # Map to frontend ScalperStatus shape
            return {
                "enabled": raw.get("enabled", False),
                "current_group": 0,
                "total_groups": len(raw.get("groups", [])),
                "group_signals": {},
                "active_trades": [
                    {
                        "ticket": t["ticket"],
                        "symbol": t["symbol"],
                        "direction": t["direction"],
                        "entry_price": t["entry"],
                        "entry_time": "",
                        "group": t["group"],
                        "status": "open",
                        "pnl": 0,
                    }
                    for t in raw.get("open_positions", [])
                ],
                "cumulative_profit": 0,
                "total_trades": raw.get("total_trades", 0),
                "win_rate": 0,
                "last_scan": raw.get("last_scan", ""),
            }
    except Exception:
        pass

    # Fallback: return disabled status
    return {
        "enabled": False,
        "current_group": 0,
        "total_groups": 7,
        "group_signals": {},
        "active_trades": [],
        "cumulative_profit": 0,
        "total_trades": 0,
        "win_rate": 0,
        "last_scan": "",
    }
