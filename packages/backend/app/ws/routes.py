from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.models import ErrorEvent, SubscribeAck, SubscribeRequest
from app.ws.hub import hub

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    try:
        while True:
            data = await ws.receive_json()
            try:
                req = SubscribeRequest.model_validate(data)
            except Exception:
                await ws.send_json(ErrorEvent(op="error", reason="invalid request").model_dump())
                continue

            if req.op == "subscribe":
                hub.subscribe(ws, req.symbol, req.period)
                await ws.send_json(
                    SubscribeAck(op="subscribed", symbol=req.symbol, period=req.period).model_dump()
                )
            else:
                hub.unsubscribe(ws, req.symbol, req.period)
    except WebSocketDisconnect:
        hub.remove(ws)
