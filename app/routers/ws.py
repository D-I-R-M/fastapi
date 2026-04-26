"""
app/routers/ws.py
~~~~~~~~~~~~~~~~~
WebSocket endpoint for live Journal updates.

Endpoint
--------
  WS /ws/journal

  Clients connect and receive JSON events whenever a new journal entry
  is saved. The connection stays open until the client disconnects.

Event shape
-----------
  {
    "event": "entry_added",
    "uid": "abc-123",
    "title": "My new drawing",
    "activity": "org.sugarlabs.TurtleArt",
    "mime_type": "image/png",
    "timestamp": "2024-09-01T10:00:00+00:00",
    "tags": ["art", "loops"]
  }

Also emits a "connected" handshake on connect:
  {
    "event": "connected",
    "message": "Listening for Sugar Journal updates"
  }

JavaScript usage
----------------
  const ws = new WebSocket("ws://localhost:8000/ws/journal");
  ws.onmessage = (e) => {
    const event = JSON.parse(e.data);
    console.log(event);
  };

REST endpoint
-------------
  POST /ws/journal/publish   — trigger a test event (dev only)
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from app.services.broadcaster import broadcaster

router = APIRouter(prefix="/ws", tags=["websocket"])


@router.websocket("/journal")
async def journal_ws(ws: WebSocket):
    """
    WebSocket endpoint. Connect to receive live journal entry events.
    Stays open until the client disconnects.
    """
    await broadcaster.connect(ws)
    try:
        # Send a handshake so the client knows it's connected
        await ws.send_text(json.dumps({
            "event": "connected",
            "message": "Listening for Sugar Journal updates",
            "connected_clients": broadcaster.client_count,
        }))

        # Keep the connection alive — we only push, clients don't send messages,
        # but we read to detect disconnects (receive_text raises on close)
        while True:
            await ws.receive_text()

    except WebSocketDisconnect:
        pass
    finally:
        await broadcaster.disconnect(ws)


@router.get("/journal/status", tags=["websocket"])
async def ws_status():
    """Return how many WebSocket clients are currently connected."""
    return {"connected_clients": broadcaster.client_count}


@router.post("/journal/publish", tags=["websocket"])
async def ws_publish_test(body: dict):
    """
    Dev-only endpoint to manually push a test event to all connected clients.

    Example body:
      {
        "title": "Test entry",
        "activity": "org.sugarlabs.TurtleArt"
      }
    """
    event = {
        "event": "entry_added",
        "uid": body.get("uid", "test-uid"),
        "title": body.get("title", "Test Entry"),
        "activity": body.get("activity", ""),
        "mime_type": body.get("mime_type", ""),
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "tags": body.get("tags", []),
    }
    await broadcaster.publish(event)
    return {"published": True, "clients_notified": broadcaster.client_count, "event": event}
