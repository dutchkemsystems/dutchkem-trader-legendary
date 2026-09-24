import asyncio
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from api.deps import get_current_user, get_execution_engine
from django_app.models import Position

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class PositionClose(BaseModel):
    symbol: str
    quantity: Optional[float] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _engine():
    return get_execution_engine()


def _user():
    u = get_current_user()
    if u is None:
        raise HTTPException(status_code=401, detail="No authenticated user")
    return u


def _serialize_position(pos) -> dict:
    return {
        "id": str(pos.id),
        "symbol": pos.ticker,
        "action": "BUY" if pos.quantity >= 0 else "SELL",
        "lot_size": float(pos.quantity),
        "entry_price": float(pos.avg_entry_price),
        "current_price": float(pos.current_price),
        "unrealized_pnl": float(pos.unrealized_pnl),
        "status": "open",
        "updated_at": pos.updated_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/")
async def list_positions():
    def _work():
        user = _user()
        positions = list(Position.objects.filter(user=user).order_by("-updated_at"))
        return {
            "positions": [_serialize_position(p) for p in positions],
            "count": len(positions),
        }
    return await asyncio.to_thread(_work)


@router.get("/summary")
async def position_summary():
    def _work():
        user = _user()
        engine = _engine()
        return engine.positions.get_position_summary(user)
    return await asyncio.to_thread(_work)


@router.post("/close")
async def close_position(payload: PositionClose):
    def _work():
        user = _user()
        engine = _engine()

        position = Position.objects.filter(user=user, ticker=payload.symbol.upper()).first()
        if position is None:
            raise HTTPException(status_code=404, detail=f"No open position for {payload.symbol}")

        quantity = Decimal(str(payload.quantity)) if payload.quantity is not None else None
        trade = engine.positions.close_position(position, quantity=quantity)
        if trade is None:
            raise HTTPException(status_code=500, detail="Failed to close position")

        return {
            "status": "closed",
            "ticker": payload.symbol.upper(),
            "trade": {
                "id": str(trade.id),
                "side": trade.side,
                "quantity": str(trade.quantity),
                "fill_price": str(trade.fill_price),
                "pnl": str(trade.pnl),
                "status": trade.status,
            },
        }
    return await asyncio.to_thread(_work)


@router.post("/close-all")
async def close_all_positions():
    def _work():
        user = _user()
        engine = _engine()
        trades = engine.positions.close_all_positions(user)
        return {
            "status": "closed",
            "closed_count": len(trades),
            "trades": [
                {
                    "id": str(t.id),
                    "ticker": t.ticker,
                    "side": t.side,
                    "quantity": str(t.quantity),
                    "fill_price": str(t.fill_price),
                    "pnl": str(t.pnl),
                }
                for t in trades
            ],
        }
    return await asyncio.to_thread(_work)


def _close_filtered(user, engine, filter_fn, label: str):
    """Close positions matching filter_fn(position) -> bool."""
    positions = list(Position.objects.filter(user=user).order_by("-updated_at"))
    to_close = [p for p in positions if filter_fn(p)]
    results = []
    for pos in to_close:
        trade = engine.positions.close_position(pos)
        if trade:
            results.append({
                "id": str(trade.id),
                "ticker": trade.ticker,
                "side": trade.side,
                "quantity": str(trade.quantity),
                "fill_price": str(trade.fill_price),
                "pnl": str(trade.pnl),
            })
    return {
        "status": "closed",
        "filter": label,
        "closed_count": len(results),
        "total_positions": len(positions),
        "trades": results,
    }


SCALPER_MAGIC = 20260911


@router.post("/close-winning")
async def close_winning_positions():
    """Close all positions with unrealized PnL > 0."""
    def _work():
        return _close_filtered(_user(), _engine(), lambda p: float(p.unrealized_pnl) > 0, "winning")
    return await asyncio.to_thread(_work)


@router.post("/close-losing")
async def close_losing_positions():
    """Close all positions with unrealized PnL <= 0."""
    def _work():
        return _close_filtered(_user(), _engine(), lambda p: float(p.unrealized_pnl) <= 0, "losing")
    return await asyncio.to_thread(_work)


@router.post("/close-scalps")
async def close_scalp_positions():
    """Close all positions opened by the scalper (magic=20260911)."""
    def _work():
        return _close_filtered(_user(), _engine(), lambda p: getattr(p, 'magic', 0) == SCALPER_MAGIC, "scalps")
    return await asyncio.to_thread(_work)
