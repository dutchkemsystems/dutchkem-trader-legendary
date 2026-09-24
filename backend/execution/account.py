from decimal import Decimal
from typing import Optional

try:
    from django.contrib.auth.models import User
except Exception:
    User = type("User", (), {"__init__": lambda *a, **kw: None})

try:
    from django.utils import timezone
except Exception:
    from datetime import timezone as _tz, datetime

    class timezone:
        @staticmethod
        def now():
            return datetime.now(_tz.utc)

        @staticmethod
        def utc():
            return _tz.utc


from django_app.models import AccountConfig
from execution.broker import AccountInfo, BaseBroker


class AccountManager:
    def __init__(self, broker: BaseBroker):
        self.broker = broker
        self._config: Optional[AccountConfig] = None

    def initialize(self, user: User, force_type: Optional[str] = None) -> AccountConfig:
        config, _ = AccountConfig.objects.get_or_create(
            user=user,
            defaults={"broker": AccountConfig.Broker.MT5},
        )
        self._config = config

        if self.broker.is_connected():
            info = self.broker.get_account_info()
            self._sync_account_info(info, force_type=force_type)

        return config

    def _sync_account_info(self, info: AccountInfo, force_type: Optional[str] = None):
        if self._config is None:
            raise RuntimeError("AccountManager not initialized")

        self._config.account_number = info.account_number
        self._config.balance = info.balance
        self._config.equity = info.equity
        self._config.margin = info.margin
        self._config.free_margin = info.free_margin
        self._config.leverage = info.leverage
        self._config.currency = info.currency
        self._config.is_connected = True
        self._config.last_synced = timezone.now()

        if force_type:
            self._config.account_type = force_type
        elif self._config.account_type is None:
            self._config.account_type = (
                AccountConfig.AccountType.CENT
                if info.balance < Decimal("1000")
                else AccountConfig.AccountType.STANDARD
            )

        self._config.save()

    def get_config(self) -> Optional[AccountConfig]:
        return self._config

    def is_cent_account(self) -> bool:
        if self._config is None:
            return False
        return self._config.account_type == AccountConfig.AccountType.CENT

    def get_pip_value(self) -> Decimal:
        return Decimal("0.01") if self.is_cent_account() else Decimal("0.10")

    def get_min_lot(self) -> Decimal:
        return Decimal("0.01")

    def get_max_lot(self) -> Decimal:
        return Decimal("10") if self.is_cent_account() else Decimal("100")

    def refresh(self):
        if self._config is None:
            raise RuntimeError("AccountManager not initialized")
        if self.broker.is_connected():
            info = self.broker.get_account_info()
            self._sync_account_info(info)
