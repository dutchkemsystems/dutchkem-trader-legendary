import pytest
import os
from unittest.mock import patch


class TestBrokerConfig:
    def test_default_simulation_mode(self):
        """Without env vars, should default to simulation mode."""
        with patch.dict(os.environ, {}, clear=True):
            from config.broker_config import BrokerConfig
            cfg = BrokerConfig.from_env()
            assert cfg.simulation_mode is True

    def test_live_mode_when_credentials_set(self):
        """With all credentials set, simulation_mode should be False."""
        env = {
            "MT5_LOGIN": "12345678",
            "MT5_PASSWORD": "secret",
            "MT5_SERVER": "Exness-MT5Trial",
        }
        with patch.dict(os.environ, env, clear=True):
            from config.broker_config import BrokerConfig
            cfg = BrokerConfig.from_env()
            assert cfg.simulation_mode is False
            assert cfg.login == "12345678"
            assert cfg.password == "secret"
            assert cfg.server == "Exness-MT5Trial"

    def test_partial_credentials_still_simulation(self):
        """With only some credentials, should still be simulation mode."""
        env = {"MT5_LOGIN": "12345678"}
        with patch.dict(os.environ, env, clear=True):
            from config.broker_config import BrokerConfig
            cfg = BrokerConfig.from_env()
            assert cfg.simulation_mode is True

    def test_custom_mt5_path(self):
        """Should accept custom MT5 terminal path."""
        env = {
            "MT5_LOGIN": "12345678",
            "MT5_PASSWORD": "secret",
            "MT5_SERVER": "Exness-MT5Trial",
            "MT5_PATH": "C:\\Program Files\\MetaTrader 5\\terminal64.exe",
        }
        with patch.dict(os.environ, env, clear=True):
            from config.broker_config import BrokerConfig
            cfg = BrokerConfig.from_env()
            assert cfg.mt5_path == "C:\\Program Files\\MetaTrader 5\\terminal64.exe"

    def test_magic_number_default(self):
        from config.broker_config import BrokerConfig
        cfg = BrokerConfig.from_env()
        assert cfg.magic_number == 234000

    def test_max_slippage_default(self):
        from config.broker_config import BrokerConfig
        cfg = BrokerConfig.from_env()
        assert cfg.max_slippage == 10
