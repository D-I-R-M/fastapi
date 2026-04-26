"""
app/services/broadcaster.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~
A lightweight in-process pub/sub broadcaster for WebSocket clients.

When a new journal entry is saved (via the datastore adapter or the D-Bus
Updated signal), call broadcaster.publish(event) and every connected
WebSocket client receives the JSON event instantly.

Usage
-----
    from app.services.broadcaster import broadcaster

    # Push an event to all connected clients
    await broadcaster.publish({
        "event": "entry_added",
        "uid": "abc-123",
        "title": "My new drawing",
        "activity": "org.sugarlabs.TurtleArt",
    })

    # Connect a WebSocket client
    await broadcaster.connect(websocket)

    # Disconnect a WebSocket client
    await broadcaster.disconnect(websocket)
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket

log = logging.getLogger(__name__)


class Broadcaster:
    def __init__(self) -> None:
        # All currently connected WebSocket clients
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)
        log.info("WebSocket client connected. Total: %d", len(self._clients))

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)
        log.info("WebSocket client disconnected. Total: %d", len(self._clients))

    async def publish(self, event: dict[str, Any]) -> None:
        """Send a JSON event to every connected client."""
        if not self._clients:
            return

        message = json.dumps(event)
        # Copy the set so we can mutate it while iterating
        async with self._lock:
            clients = set(self._clients)

        dead: set[WebSocket] = set()
        for ws in clients:
            try:
                await ws.send_text(message)
            except Exception:
                # Client disconnected ungracefully
                dead.add(ws)

        # Clean up dead connections
        if dead:
            async with self._lock:
                self._clients -= dead
            log.info("Removed %d dead WebSocket connection(s)", len(dead))

    @property
    def client_count(self) -> int:
        return len(self._clients)


# Global singleton — imported everywhere
broadcaster = Broadcaster()
