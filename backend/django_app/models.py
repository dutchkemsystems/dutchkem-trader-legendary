"""
Lightweight in-memory store replacing Django ORM models.
Provides AccountConfig and Position with the same interface used by route handlers.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal


class _MemoryStore:
    """Simple dict-backed store with get_or_create / save semantics."""

    def __init__(self):
        self._items: dict[tuple, object] = {}

    def get_or_create(self, defaults=None, **kwargs):
        key = tuple(sorted(kwargs.items()))
        if key in self._items:
            return self._items[key], False
        obj = _Model(defaults or {}, **kwargs)
        self._items[key] = obj
        return obj, True

    def filter(self, **kwargs):
        return [
            obj
            for obj in self._items.values()
            if all(getattr(obj, k, None) == v for k, v in kwargs.items())
        ]


class _Model:
    def __init__(self, defaults=None, **kwargs):
        self.id = uuid.uuid4()
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)
        for k, v in (defaults or {}).items():
            setattr(self, k, v)
        for k, v in kwargs.items():
            setattr(self, k, v)

    def save(self):
        self.updated_at = datetime.now(timezone.utc)


# ── AccountConfig ──


class _AccountConfig:
    class Broker:
        MT4 = "MT4"
        MT5 = "MT5"

    class AccountType:
        CENT = "CENT"
        STANDARD = "STANDARD"

    objects = _MemoryStore()

    def __init__(self, **kwargs):
        self.id = uuid.uuid4()
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)
        self.broker = kwargs.get("broker", "MT5")
        self.account_type = kwargs.get("account_type")
        self.account_number = kwargs.get("account_number", "")
        self.balance = kwargs.get("balance", Decimal("0"))
        self.equity = kwargs.get("equity", Decimal("0"))
        self.margin = kwargs.get("margin", Decimal("0"))
        self.free_margin = kwargs.get("free_margin", Decimal("0"))
        self.leverage = kwargs.get("leverage", 100)
        self.currency = kwargs.get("currency", "USD")
        self.is_connected = kwargs.get("is_connected", False)
        self.simulation_mode = kwargs.get("simulation_mode", True)
        self.last_synced = kwargs.get("last_synced")
        self.user = kwargs.get("user")

    def save(self):
        self.updated_at = datetime.now(timezone.utc)


AccountConfig = _AccountConfig


# ── Position ──


class _Position:
    objects = _MemoryStore()

    def __init__(self, **kwargs):
        self.id = uuid.uuid4()
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)
        self.ticker = kwargs.get("ticker", "")
        self.quantity = kwargs.get("quantity", Decimal("0"))
        self.avg_entry_price = kwargs.get("avg_entry_price", Decimal("0"))
        self.current_price = kwargs.get("current_price", Decimal("0"))
        self.unrealized_pnl = kwargs.get("unrealized_pnl", Decimal("0"))
        self.user = kwargs.get("user")

    def save(self):
        self.updated_at = datetime.now(timezone.utc)


Position = _Position


# ── Trade ──


class _Trade:
    class Status:
        PENDING = "PENDING"
        SUBMITTED = "SUBMITTED"
        PARTIAL = "PARTIAL"
        EXECUTED = "EXECUTED"
        CANCELLED = "CANCELLED"
        FAILED = "FAILED"

    class Side:
        BUY = "BUY"
        SELL = "SELL"

    class OrderType:
        MARKET = "MARKET"
        LIMIT = "LIMIT"
        STOP = "STOP"
        STOP_LIMIT = "STOP_LIMIT"

    objects = _MemoryStore()

    def __init__(self, **kwargs):
        self.id = uuid.uuid4()
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)
        self.user = kwargs.get("user")
        self.ticker = kwargs.get("ticker", "")
        self.side = kwargs.get("side", "BUY")
        self.order_type = kwargs.get("order_type", "MARKET")
        self.quantity = kwargs.get("quantity", Decimal("0"))
        self.price = kwargs.get("price", Decimal("0"))
        self.stop_loss = kwargs.get("stop_loss")
        self.take_profit = kwargs.get("take_profit")
        self.broker_order_id = kwargs.get("broker_order_id")
        self.filled_quantity = kwargs.get("filled_quantity", Decimal("0"))
        self.fill_price = kwargs.get("fill_price")
        self.commission = kwargs.get("commission", Decimal("0"))
        self.pnl = kwargs.get("pnl", Decimal("0"))
        self.notes = kwargs.get("notes", "")
        self.status = kwargs.get("status", "PENDING")
        self.executed_at = kwargs.get("executed_at")

    def save(self):
        self.updated_at = datetime.now(timezone.utc)

    @property
    def aggregate(self):
        """Stub for .aggregate(total=Sum(...)) pattern."""
        return lambda *a, **kw: {}

    def filter(self, **kwargs):
        return []


Trade = _Trade


# ── ConsensusResult ──


class _ConsensusResult:
    objects = _MemoryStore()

    def __init__(self, **kwargs):
        self.id = uuid.uuid4()
        self.created_at = datetime.now(timezone.utc)
        self.user = kwargs.get("user")
        self.ticker = kwargs.get("ticker", "")
        self.consensus_signal = kwargs.get("consensus_signal", "HOLD")
        self.weight = kwargs.get("weight", 0.0)
        self.reasoning = kwargs.get("reasoning", "")

    def save(self):
        self.updated_at = datetime.now(timezone.utc)


ConsensusResult = _ConsensusResult
