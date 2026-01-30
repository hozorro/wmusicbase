# -*- encoding: utf-8 -*-
'''
@File      :   ws.py
@Time      :   2026/01/15 22:05:48
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2026 WEYECO <enauvy@qq.com>
@Desc      :   websocket
'''


import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from app.core.deps import require_websocket_admin
from app.core.state import system_state
from app.models.user import User

router = APIRouter()

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                self.disconnect(connection)

manager = ConnectionManager()

@router.websocket('/scan-progress')
async def scan_progress_websocket(websocket: WebSocket, user: User = Depends(require_websocket_admin)):
    await manager.connect(websocket)
    try:
        while True:
            await asyncio.sleep(1)
            if system_state.is_scanning:
                await manager.broadcast({
                    'type': 'scan_progress',
                    'data': system_state.scan_progress
                })
            else:
                await manager.broadcast({
                    'type': 'scan_complete',
                    'data': None
                })
                break
    except WebSocketDisconnect:
        manager.disconnect(websocket)
