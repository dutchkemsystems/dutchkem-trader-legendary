from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, List
import asyncio


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, channel: str):
        await websocket.accept()
        if channel not in self.active_connections:
            self.active_connections[channel] = []
        self.active_connections[channel].append(websocket)

    def disconnect(self, websocket: WebSocket, channel: str):
        if channel in self.active_connections:
            self.active_connections[channel].remove(websocket)

    async def broadcast(self, channel: str, message: dict):
        if channel in self.active_connections:
            for connection in self.active_connections[channel]:
                try:
                    await connection.send_json(message)
                except Exception:
                    pass


manager = ConnectionManager()


async def market_websocket(websocket: WebSocket, symbol: str):
    await manager.connect(websocket, f"market:{symbol}")
    try:
        while True:
            await asyncio.sleep(1)
            await websocket.send_json({
                "symbol": symbol,
                "price": 1.0890,
                "timestamp": "2026-09-05T00:00:00Z",
            })
    except WebSocketDisconnect:
        manager.disconnect(websocket, f"market:{symbol}")


async def trades_websocket(websocket: WebSocket):
    await manager.connect(websocket, "trades")
    try:
        while True:
            await asyncio.sleep(1)
            await websocket.send_json({"type": "heartbeat"})
    except WebSocketDisconnect:
        manager.disconnect(websocket, "trades")


async def consensus_websocket(websocket: WebSocket):
    await manager.connect(websocket, "consensus")
    try:
        while True:
            await asyncio.sleep(1)
            await websocket.send_json({"type": "heartbeat"})
    except WebSocketDisconnect:
        manager.disconnect(websocket, "consensus")
