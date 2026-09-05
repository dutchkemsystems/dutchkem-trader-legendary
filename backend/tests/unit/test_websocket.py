import pytest
from api.websocket.handlers import ConnectionManager

def test_connection_manager_creation():
    manager = ConnectionManager()
    assert hasattr(manager, 'active_connections')
    assert manager.active_connections == {}

def test_connection_manager_disconnect_empty():
    manager = ConnectionManager()
    # Should not crash when disconnecting from empty channel
    from unittest.mock import MagicMock
    mock_ws = MagicMock()
    manager.disconnect(mock_ws, "nonexistent")
    # No assertion needed — just verify it doesn't crash

def test_connection_manager_broadcast_empty():
    import asyncio
    manager = ConnectionManager()
    # Should not crash when broadcasting to empty channel
    asyncio.run(manager.broadcast("nonexistent", {"test": "data"}))
