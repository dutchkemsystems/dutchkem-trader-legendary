from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional, List, Dict, Any


class OrderType(Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


class OrderSide(Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(Enum):
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    FILLED = "FILLED"
    PARTIAL = "PARTIAL"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


@dataclass
class BrokerOrder:
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: Decimal
    price: Optional[Decimal] = None
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None
    trailing_stop: Optional[Decimal] = None
    magic_number: int = 0
    comment: str = ""

    def __post_init__(self):
        if not isinstance(self.side, OrderSide):
            self.side = OrderSide(self.side)
        if not isinstance(self.order_type, OrderType):
            self.order_type = OrderType(self.order_type)
        if self.quantity <= 0:
            raise ValueError("Quantity must be positive")
        if self.order_type in (OrderType.LIMIT, OrderType.STOP, OrderType.STOP_LIMIT):
            if self.price is None:
                raise ValueError(f"{self.order_type.value} order requires a price")


@dataclass
class BrokerFill:
    order_id: str
    symbol: str
    side: OrderSide
    quantity: Decimal
    price: Decimal
    commission: Decimal
    slippage: Decimal
    timestamp: datetime
    broker_order_id: str

    def __post_init__(self):
        if not isinstance(self.side, OrderSide):
            self.side = OrderSide(self.side)
        if self.timestamp.tzinfo is None:
            self.timestamp = self.timestamp.replace(tzinfo=timezone.utc)


@dataclass
class BrokerPosition:
    ticket: int
    symbol: str
    side: OrderSide
    quantity: Decimal
    open_price: Decimal
    current_price: Decimal
    unrealized_pnl: Decimal
    swap: Decimal
    commission: Decimal
    open_time: datetime
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None
    magic_number: int = 0
    comment: str = ""

    def __post_init__(self):
        if not isinstance(self.side, OrderSide):
            self.side = OrderSide(self.side)
        if self.open_time.tzinfo is None:
            self.open_time = self.open_time.replace(tzinfo=timezone.utc)


@dataclass
class AccountInfo:
    account_number: str
    balance: Decimal
    equity: Decimal
    margin: Decimal
    free_margin: Decimal
    leverage: int
    currency: str
    account_type: str
    profit: Decimal


class BaseBroker(ABC):
    @abstractmethod
    def connect(self, account_number: str, password: str, server: str) -> bool:
        ...

    @abstractmethod
    def disconnect(self) -> None:
        ...

    @abstractmethod
    def is_connected(self) -> bool:
        ...

    @abstractmethod
    def get_account_info(self) -> AccountInfo:
        ...

    @abstractmethod
    def place_order(self, order: BrokerOrder) -> BrokerFill:
        ...

    @abstractmethod
    def modify_position(
        self,
        ticket: int,
        stop_loss: Optional[Decimal] = None,
        take_profit: Optional[Decimal] = None,
    ) -> bool:
        ...

    @abstractmethod
    def close_position(
        self, ticket: int, quantity: Optional[Decimal] = None
    ) -> BrokerFill:
        ...

    @abstractmethod
    def get_positions(self) -> List[BrokerPosition]:
        ...

    @abstractmethod
    def get_position(self, ticket: int) -> Optional[BrokerPosition]:
        ...

    @abstractmethod
    def get_tick(self, symbol: str) -> Dict[str, Any]:
        ...

    @abstractmethod
    def get_symbol_info(self, symbol: str) -> Dict[str, Any]:
        ...
