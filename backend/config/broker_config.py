"""Broker configuration — reads MT5 credentials from environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class BrokerConfig:
    login: str = ""
    password: str = ""
    server: str = ""
    mt5_path: str = ""
    magic_number: int = 234000
    max_slippage: int = 10

    @property
    def simulation_mode(self) -> bool:
        return not all([self.login, self.password, self.server])

    @classmethod
    def from_env(cls) -> BrokerConfig:
        return cls(
            login=os.environ.get("MT5_LOGIN", ""),
            password=os.environ.get("MT5_PASSWORD", ""),
            server=os.environ.get("MT5_SERVER", ""),
            mt5_path=os.environ.get("MT5_PATH", ""),
            magic_number=int(os.environ.get("MT5_MAGIC", "234000")),
            max_slippage=int(os.environ.get("MT5_SLIPPAGE", "10")),
        )
