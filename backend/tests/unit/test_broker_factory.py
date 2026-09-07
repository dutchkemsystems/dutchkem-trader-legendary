import pytest
from unittest.mock import patch
from config.broker_config import BrokerConfig


class TestBrokerFactory:
    def test_create_simulation_broker(self):
        from execution.broker_factory import create_broker
        cfg = BrokerConfig()
        broker = create_broker(cfg)
        assert broker is not None
        assert broker.is_connected() is False

    def test_create_live_broker(self):
        from execution.broker_factory import create_broker
        cfg = BrokerConfig(login="123", password="secret", server="Exness-MT5Trial")
        broker = create_broker(cfg)
        assert broker is not None

    def test_factory_returns_mt5_connector(self):
        from execution.broker_factory import create_broker
        from execution.mt5_connector import MT5Connector
        cfg = BrokerConfig()
        broker = create_broker(cfg)
        assert isinstance(broker, MT5Connector)

    def test_factory_simulation_mode_when_no_credentials(self):
        from execution.broker_factory import create_broker
        cfg = BrokerConfig.from_env()
        with patch.dict("os.environ", {}, clear=True):
            cfg = BrokerConfig.from_env()
            broker = create_broker(cfg)
            assert broker.is_connected() is False

    def test_factory_stores_config(self):
        from execution.broker_factory import create_broker
        cfg = BrokerConfig(magic_number=999999)
        broker = create_broker(cfg)
        assert hasattr(broker, '_config')
        assert broker._config.magic_number == 999999
