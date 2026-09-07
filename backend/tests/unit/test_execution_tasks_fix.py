"""Tests for execution_tasks.py — verify MT5BrokerConnector references are fixed."""
import pytest
from unittest.mock import patch, MagicMock


def test_get_broker_returns_mt5connector_instance():
    """_get_broker should return an MT5Connector, not reference MT5BrokerConnector."""
    from execution.mt5_connector import MT5Connector
    from tasks import execution_tasks

    # Reset the global to force re-creation
    execution_tasks._broker = None

    broker = execution_tasks._get_broker()
    assert isinstance(broker, MT5Connector)
    assert broker._connected is False


def test_get_broker_singleton():
    """_get_broker should return the same instance on repeated calls."""
    from tasks import execution_tasks

    execution_tasks._broker = None
    b1 = execution_tasks._get_broker()
    b2 = execution_tasks._get_broker()
    assert b1 is b2


def test_get_broker_return_type_annotation():
    """_get_broker return type should be MT5Connector, not MT5BrokerConnector."""
    import inspect
    from tasks import execution_tasks

    sig = inspect.signature(execution_tasks._get_broker)
    return_annotation = sig.return_annotation
    # Should reference MT5Connector, not the non-existent MT5BrokerConnector
    from execution.mt5_connector import MT5Connector
    assert return_annotation is MT5Connector or return_annotation == "MT5Connector"
