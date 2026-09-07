"""Broker API routes — connection management, account info, and AccountConfig sync."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from django.utils import timezone

from api.deps import get_broker, get_current_user
from config.broker_config import BrokerConfig
from django_app.models import AccountConfig

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


class BrokerConfigResponse(BaseModel):
    broker: str
    account_number: str
    account_type: str | None = None
    balance: str
    equity: str
    margin: str
    free_margin: str
    leverage: int
    currency: str
    is_connected: bool
    simulation_mode: bool
    last_synced: str | None = None


class BrokerSyncResponse(BaseModel):
    synced: bool
    account_number: str
    balance: str
    is_connected: bool
    simulation_mode: bool
    last_synced: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_or_create_config(user):
    config, _ = AccountConfig.objects.get_or_create(
        user=user,
        defaults={"broker": AccountConfig.Broker.MT5},
    )
    return config


def _sync_config_from_broker(config, broker, broker_config):
    """Sync AccountConfig fields from broker state."""
    config.is_connected = broker.is_connected()
    config.simulation_mode = broker_config.simulation_mode

    if broker.is_connected():
        info = broker.get_account_info()
        config.account_number = info.account_number
        config.balance = info.balance
        config.equity = info.equity
        config.margin = info.margin
        config.free_margin = info.free_margin
        config.leverage = info.leverage
        config.currency = info.currency

        if config.account_type is None:
            from decimal import Decimal
            config.account_type = (
                AccountConfig.AccountType.CENT
                if info.balance < Decimal("1000")
                else AccountConfig.AccountType.STANDARD
            )

    config.last_synced = timezone.now()
    config.save()


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

    # Sync AccountConfig
    user = get_current_user()
    config = _get_or_create_config(user)
    broker_config = BrokerConfig.from_env()
    _sync_config_from_broker(config, broker, broker_config)

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

    # Sync AccountConfig
    user = get_current_user()
    config = _get_or_create_config(user)
    broker_config = BrokerConfig.from_env()
    _sync_config_from_broker(config, broker, broker_config)

    return {"status": "disconnected"}


@router.get("/account", response_model=BrokerAccountResponse)
def broker_account():
    """Get account info from the broker. Requires active connection."""
    broker = get_broker()
    if not broker.is_connected():
        raise HTTPException(status_code=503, detail="Broker not connected")

    info = broker.get_account_info()

    # Sync AccountConfig
    user = get_current_user()
    config = _get_or_create_config(user)
    broker_config = BrokerConfig.from_env()
    _sync_config_from_broker(config, broker, broker_config)

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


@router.get("/config", response_model=BrokerConfigResponse)
def broker_config():
    """Get the stored AccountConfig for the current user."""
    user = get_current_user()
    config = _get_or_create_config(user)
    return BrokerConfigResponse(
        broker=config.broker,
        account_number=config.account_number,
        account_type=config.account_type,
        balance=str(config.balance),
        equity=str(config.equity),
        margin=str(config.margin),
        free_margin=str(config.free_margin),
        leverage=config.leverage,
        currency=config.currency,
        is_connected=config.is_connected,
        simulation_mode=config.simulation_mode,
        last_synced=config.last_synced.isoformat() if config.last_synced else None,
    )


@router.post("/sync", response_model=BrokerSyncResponse)
def broker_sync():
    """Force-sync broker state into the AccountConfig model."""
    user = get_current_user()
    config = _get_or_create_config(user)
    broker = get_broker()
    broker_config = BrokerConfig.from_env()
    _sync_config_from_broker(config, broker, broker_config)
    return BrokerSyncResponse(
        synced=True,
        account_number=config.account_number,
        balance=str(config.balance),
        is_connected=config.is_connected,
        simulation_mode=config.simulation_mode,
        last_synced=config.last_synced.isoformat() if config.last_synced else None,
    )
