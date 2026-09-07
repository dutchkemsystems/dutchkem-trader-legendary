"""Broker factory — creates broker instances from config."""
from __future__ import annotations

from config.broker_config import BrokerConfig
from execution.mt5_connector import MT5Connector
from execution.broker import BaseBroker


def create_broker(config: BrokerConfig) -> BaseBroker:
    return MT5Connector(config=config)
