from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from app.services.websocket_manager import websocket_manager


router = APIRouter(tags=["websocket"])


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    user_id: str = Query(...),
    session_id: str = Query(...),
) -> None:
    if not user_id.strip() or not session_id.strip():
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    normalized_user_id = user_id.strip()
    normalized_session_id = session_id.strip()
    await websocket_manager.connect(
        websocket,
        user_id=normalized_user_id,
        session_id=normalized_session_id,
    )

    try:
        while True:
            message = await websocket.receive_json()
            response = await _handle_ws_message(
                message=message,
                user_id=normalized_user_id,
                session_id=normalized_session_id,
            )
            if response is not None:
                await websocket.send_json(response)
    except WebSocketDisconnect:
        pass
    finally:
        await websocket_manager.disconnect(
            websocket,
            user_id=normalized_user_id,
            session_id=normalized_session_id,
        )


async def _handle_ws_message(
    *,
    message: Any,
    user_id: str,
    session_id: str,
) -> dict[str, Any] | None:
    if not isinstance(message, dict):
        return {
            "type": "error",
            "error": "message_must_be_object",
        }

    message_type = str(message.get("type") or "").strip().lower()
    if message_type in {"heartbeat", "ping"}:
        return await websocket_manager.heartbeat(
            user_id=user_id,
            session_id=session_id,
        )

    return {
        "type": "ack",
        "message_type": message_type or "unknown",
    }

