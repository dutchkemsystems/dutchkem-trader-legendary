from enum import Enum
from datetime import datetime, timedelta, timezone


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(self, daily_loss_limit: float = 5.0, cooldown_minutes: int = 60):
        self.daily_loss_limit = daily_loss_limit
        self.cooldown_minutes = cooldown_minutes
        self.state = CircuitState.CLOSED
        self.daily_pnl = 0.0
        self.opened_at = None
        self.successful_recoveries = 0

    def record_loss(self, loss_pct: float):
        self.daily_pnl -= abs(loss_pct)
        if self.daily_pnl <= -self.daily_loss_limit:
            self.state = CircuitState.OPEN
            self.opened_at = datetime.now(timezone.utc)

    def record_profit(self, profit_pct: float):
        self.daily_pnl += abs(profit_pct)
        if self.state == CircuitState.OPEN:
            if self.opened_at and datetime.now(timezone.utc) - self.opened_at > timedelta(minutes=self.cooldown_minutes):
                self.state = CircuitState.HALF_OPEN
        elif self.state == CircuitState.HALF_OPEN:
            self.successful_recoveries += 1
            if self.successful_recoveries >= 2:
                self.state = CircuitState.CLOSED
                self.daily_pnl = 0.0
                self.successful_recoveries = 0

    def can_trade(self) -> bool:
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.HALF_OPEN:
            return True
        if self.state == CircuitState.OPEN:
            if self.opened_at and datetime.now(timezone.utc) - self.opened_at > timedelta(minutes=self.cooldown_minutes):
                self.state = CircuitState.HALF_OPEN
                return True
            return False
        return False

    def reset(self):
        self.state = CircuitState.CLOSED
        self.daily_pnl = 0.0
        self.opened_at = None
        self.successful_recoveries = 0
