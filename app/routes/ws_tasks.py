import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.services.telegram_service import telegram_service
from app.services.ws_manager import ws_manager
import json

router = APIRouter(prefix="/ws")


@router.websocket("/tasks/{user_id}")
async def websocket_tasks(ws: WebSocket, user_id: str):
    await ws.accept()
    await ws_manager.connect(user_id, ws)

    try:
        # Send snapshot immediately
        tasks_ui = telegram_service.list_all_tasks(user_id)
        await ws.send_text(json.dumps({"event": "snapshot", "tasks": tasks_ui}))

        while True:
            # Optional: keepalive ping
            await asyncio.sleep(30)
            await ws.send_text(json.dumps({"event": "ping"}))

    except WebSocketDisconnect:
        await ws_manager.disconnect(user_id, ws)
    except Exception:
        await ws_manager.disconnect(user_id, ws)
        await ws.close()
