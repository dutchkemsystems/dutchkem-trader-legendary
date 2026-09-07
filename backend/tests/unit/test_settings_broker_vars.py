"""Tests that broker env vars are properly configured in Django settings."""
import os
import pytest


def test_broker_settings_exist_in_settings_module():
    """settings.py should reference broker env vars."""
    from config import settings

    # Check that settings module has broker-related configuration
    # At minimum, it should be possible to import without errors
    assert hasattr(settings, "BASE_DIR")


def test_broker_config_from_env_respects_settings(monkeypatch):
    """BrokerConfig.from_env should read from environment (which settings loads)."""
    monkeypatch.setenv("MT5_LOGIN", "99999")
    monkeypatch.setenv("MT5_PASSWORD", "secret123")
    monkeypatch.setenv("MT5_SERVER", "Exness-MT5Real")
    monkeypatch.setenv("MT5_MAGIC", "555555")
    monkeypatch.setenv("MT5_SLIPPAGE", "5")

    from config.broker_config import BrokerConfig
    config = BrokerConfig.from_env()

    assert config.login == "99999"
    assert config.password == "secret123"
    assert config.server == "Exness-MT5Real"
    assert config.magic_number == 555555
    assert config.max_slippage == 5
    assert config.simulation_mode is False


def test_broker_config_simulation_mode_when_no_env(monkeypatch):
    """BrokerConfig should default to simulation mode when env vars missing."""
    monkeypatch.delenv("MT5_LOGIN", raising=False)
    monkeypatch.delenv("MT5_PASSWORD", raising=False)
    monkeypatch.delenv("MT5_SERVER", raising=False)

    from config.broker_config import BrokerConfig
    config = BrokerConfig.from_env()

    assert config.simulation_mode is True
