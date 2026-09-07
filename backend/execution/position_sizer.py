from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from execution.account import AccountManager

PIP_MAP = {
    "JPY": Decimal("0.01"),
    "XAUUSD": Decimal("0.01"),
    "XAGUSD": Decimal("0.001"),
}
DEFAULT_PIP_SIZE = Decimal("0.0001")

CONFIDENCE_RISK_MAP = [
    (0.9, Decimal("2.0")),
    (0.8, Decimal("1.5")),
    (0.7, Decimal("1.0")),
    (0.0, Decimal("0.5")),
]

CENT_PIP_VALUE = Decimal("0.10")
STANDARD_PIP_VALUE = Decimal("10.00")


class PositionSizer:
    def __init__(self, account_manager: AccountManager):
        self.account = account_manager

    def _pip_size(self, symbol: str) -> Decimal:
        sym = symbol.upper()
        for key, val in PIP_MAP.items():
            if key in sym:
                return val
        return DEFAULT_PIP_SIZE

    def _pip_value_per_lot(self) -> Decimal:
        if self.account.is_cent_account():
            return CENT_PIP_VALUE
        return STANDARD_PIP_VALUE

    def calculate_lot_size(
        self,
        entry_price: Decimal,
        stop_loss: Decimal,
        risk_percent: Decimal = Decimal("1.0"),
        symbol: str = "EURUSD",
    ) -> Decimal:
        config = self.account.get_config()
        if config is None:
            return self.account.get_min_lot()

        balance = Decimal(str(config.balance))
        pip_size = self._pip_size(symbol)
        pip_value_per_lot = self._pip_value_per_lot()

        risk_amount = balance * (risk_percent / Decimal("100"))
        stop_distance = abs(entry_price - stop_loss)
        stop_pips = stop_distance / pip_size

        if stop_pips <= 0:
            return self.account.get_min_lot()

        value_per_pip = pip_value_per_lot / Decimal("10")
        lot_size = risk_amount / (stop_pips * value_per_pip)

        lot_size = lot_size.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        min_lot = self.account.get_min_lot()
        max_lot = self.account.get_max_lot()
        lot_size = max(min_lot, min(lot_size, max_lot))

        return lot_size

    def calculate_lot_size_from_confidence(
        self,
        entry_price: Decimal,
        stop_loss: Decimal,
        confidence: float,
        symbol: str = "EURUSD",
    ) -> Decimal:
        risk_percent = Decimal("0.5")
        for threshold, pct in CONFIDENCE_RISK_MAP:
            if confidence >= float(threshold):
                risk_percent = pct
                break

        return self.calculate_lot_size(entry_price, stop_loss, risk_percent, symbol)

    def calculate_dynamic_stop_loss(
        self,
        entry_price: Decimal,
        side: str,
        atr: Optional[Decimal] = None,
        symbol: str = "EURUSD",
    ) -> Decimal:
        if atr is not None and atr > 0:
            distance = Decimal("2") * atr
        else:
            pip_size = self._pip_size(symbol)
            distance = Decimal("50") * pip_size

        if side.lower() == "buy":
            return entry_price - distance
        return entry_price + distance

    def calculate_take_profit(
        self,
        entry_price: Decimal,
        stop_loss: Decimal,
        side: str,
        risk_reward_ratio: Decimal = Decimal("2.0"),
    ) -> Decimal:
        risk = abs(entry_price - stop_loss)
        reward = risk * risk_reward_ratio

        if side.lower() == "buy":
            return entry_price + reward
        return entry_price - reward
