import asyncio
from decimal import Decimal, InvalidOperation
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from api.deps import get_current_user, get_execution_engine

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class TradeCreate(BaseModel):
    symbol: str
    action: str
    lot_size: Optional[float] = None
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    order_type: str = "MARKET"
    confidence: Optional[float] = None
    consensus_id: Optional[str] = None


class TradeClose(BaseModel):
    trade_id: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_decimal(value: Optional[float]) -> Optional[Decimal]:
    if value is None:
        return None
    return Decimal(str(value))


def _serialize_trade(trade) -> dict:
    return {
        "id": str(trade.id),
        "symbol": trade.ticker,
        "action": trade.side,
        "order_type": trade.order_type,
        "lot_size": float(trade.quantity),
        "entry_price": float(trade.price),
        "stop_loss": float(trade.stop_loss) if trade.stop_loss else None,
        "take_profit": float(trade.take_profit) if trade.take_profit else None,
        "fill_price": float(trade.fill_price) if trade.fill_price else None,
        "pnl": float(trade.pnl),
        "commission": float(trade.commission),
        "slippage": float(trade.slippage),
        "status": trade.status,
        "notes": trade.notes,
        "executed_at": trade.executed_at.isoformat() if trade.executed_at else None,
        "created_at": trade.created_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/")
async def list_trades(limit: int = Query(50, ge=1, le=500)):
    def _work():
        user = get_current_user()
        if user is None:
            raise HTTPException(status_code=401, detail="No authenticated user")
        engine = get_execution_engine()
        trades = engine.get_trade_history(user, limit=limit)
        return {"trades": trades, "count": len(trades)}
    return await asyncio.to_thread(_work)


@router.post("/")
async def create_trade(payload: TradeCreate):
    def _work():
        user = get_current_user()
        if user is None:
            raise HTTPException(status_code=401, detail="No authenticated user")

        if payload.action.upper() not in ("BUY", "SELL"):
            raise HTTPException(status_code=400, detail="action must be BUY or SELL")

        engine = get_execution_engine()

        try:
            trade = engine.execute_trade(
                user=user,
                symbol=payload.symbol.upper(),
                side=payload.action.upper(),
                lot_size=_to_decimal(payload.lot_size),
                entry_price=_to_decimal(payload.entry_price),
                stop_loss=_to_decimal(payload.stop_loss),
                take_profit=_to_decimal(payload.take_profit),
                order_type=payload.order_type.upper(),
                confidence=payload.confidence,
                consensus_id=payload.consensus_id,
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

        serialized = _serialize_trade(trade)
        return {"id": serialized["id"], "status": serialized["status"], "trade": serialized}
    return await asyncio.to_thread(_work)


@router.get("/summary/daily")
async def daily_summary():
    def _work():
        user = get_current_user()
        if user is None:
            raise HTTPException(status_code=401, detail="No authenticated user")
        engine = get_execution_engine()
        return engine.get_daily_summary(user)
    return await asyncio.to_thread(_work)


@router.get("/summary/monthly")
async def monthly_summary():
    def _work():
        user = get_current_user()
        if user is None:
            raise HTTPException(status_code=401, detail="No authenticated user")
        engine = get_execution_engine()
        return engine.get_monthly_summary(user)
    return await asyncio.to_thread(_work)


@router.post("/close")
async def close_trade(payload: TradeClose):
    def _work():
        user = get_current_user()
        if user is None:
            raise HTTPException(status_code=401, detail="No authenticated user")
        engine = get_execution_engine()
        trade = engine.close_trade(payload.trade_id, user)
        if trade is None:
            raise HTTPException(status_code=404, detail="Trade not found or already closed")
        return _serialize_trade(trade)
    return await asyncio.to_thread(_work)
