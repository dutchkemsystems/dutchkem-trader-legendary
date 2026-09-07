"""Broker API routes — connection management and account info."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.deps import get_broker

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class BrokerConnectRequest(BaseModel):
    account_number: str
    password: str
    server: str


class BrokerStatusResponse(BaseModel):
    connected: bool
    account_number: str | None = None
    server: str | None = None


class BrokerAccountResponse(BaseModel):
    account_number: str
    balance: str
    equity: str
    free_margin: str
    leverage: int
    currency: str
    account_type: str
    profit: str


class BrokerConnectResponse(BaseModel):
    status: str
    connected: bool
    account_number: str | None = None
    server: str | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/status", response_model=BrokerStatusResponse)
def broker_status():
    """Return current broker connection status."""
    broker = get_broker()
    connected = broker.is_connected()
    return BrokerStatusResponse(
        connected=connected,
        account_number=broker._account_number if connected else None,
        server=broker._server if connected else None,
    )


@router.post("/connect", response_model=BrokerConnectResponse)
def broker_connect(payload: BrokerConnectRequest):
    """Connect to the broker with provided credentials."""
    broker = get_broker()
    success = broker.connect(payload.account_number, payload.password, payload.server)

    if not success:
        return BrokerConnectResponse(
            status="failed",
            connected=False,
        )

    account = broker.get_account_info()
    return BrokerConnectResponse(
        status="connected",
        connected=True,
        account_number=account.account_number,
        server=payload.server,
    )


@router.post("/disconnect")
def broker_disconnect():
    """Disconnect from the broker."""
    broker = get_broker()
    broker.disconnect()
    return {"status": "disconnected"}


@router.get("/account", response_model=BrokerAccountResponse)
def broker_account():
    """Get account info from the broker. Requires active connection."""
    broker = get_broker()
    if not broker.is_connected():
        raise HTTPException(status_code=503, detail="Broker not connected")

    info = broker.get_account_info()
    return BrokerAccountResponse(
        account_number=info.account_number,
        balance=str(info.balance),
        equity=str(info.equity),
        free_margin=str(info.free_margin),
        leverage=info.leverage,
        currency=info.currency,
        account_type=info.account_type,
        profit=str(info.profit),
    )
