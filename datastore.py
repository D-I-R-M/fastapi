"""
app/adapters/datastore.py — pluggable backends for the Sugar Datastore.

Three backends are supported:

  dbus  — talks to the real Sugar Datastore over D-Bus (on-device, Linux only).
           Requires the `dbus-python` package and a running Sugar session.

  file  — reads flat JSON files from a directory (one file = one entry).
           Great for development / testing without Sugar installed.

  mock  — returns in-memory fake data; used by unit tests.

Select the backend via the DATASTORE_BACKEND environment variable.
"""
from __future__ import annotations

import json
import os
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import settings
from app.models.journal import JournalEntry, SearchQuery


# ---------------------------------------------------------------------------
# Abstract interface
# ---------------------------------------------------------------------------

class BaseDatastoreAdapter(ABC):
    @abstractmethod
    async def get_entry(self, uid: str) -> JournalEntry | None: ...

    @abstractmethod
    async def list_entries(self, query: SearchQuery) -> tuple[list[JournalEntry], int]:
        """Return (page, total_count)."""
        ...

    @abstractmethod
    async def delete_entry(self, uid: str) -> bool: ...


# ---------------------------------------------------------------------------
# D-Bus backend (real Sugar datastore)
# ---------------------------------------------------------------------------

class DBusDatastoreAdapter(BaseDatastoreAdapter):
    """
    Talks to org.laptop.sugar.DataStore over session D-Bus.
    Mirrors what jarabe/journal uses internally.

    The datastore's find() method signature is:
      find(query: dict, properties: list[str]) -> (list[dict], int)

    Each result dict contains the metadata keys listed in models/journal.py.
    """

    DBUS_SERVICE = "org.laptop.sugar.DataStore"
    DBUS_PATH = "/org/laptop/sugar/DataStore"
    DBUS_IFACE = "org.laptop.sugar.DataStore"

    def __init__(self) -> None:
        try:
            import dbus  # type: ignore
            bus = dbus.SessionBus()
            proxy = bus.get_object(self.DBUS_SERVICE, self.DBUS_PATH)
            self._ds = dbus.Interface(proxy, dbus_interface=self.DBUS_IFACE)
        except Exception as exc:
            raise RuntimeError(
                "D-Bus datastore not available. "
                "Set DATASTORE_BACKEND=mock or DATASTORE_BACKEND=file."
            ) from exc

    def _props_to_entry(self, props: dict) -> JournalEntry:
        ts_raw = props.get("timestamp", "")
        try:
            ts = datetime.fromtimestamp(float(ts_raw), tz=timezone.utc) if ts_raw else None
        except (ValueError, TypeError):
            ts = None

        tags_raw = props.get("tags", "")
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()] if tags_raw else []

        return JournalEntry(
            uid=str(props.get("uid", "")),
            title=str(props.get("title", "Untitled")),
            activity=str(props.get("activity", "")),
            activity_id=str(props.get("activity_id", "")),
            mime_type=str(props.get("mime_type", "")),
            timestamp=ts,
            filesize=int(props.get("filesize", 0) or 0),
            description=str(props.get("description", "")),
            tags=tags,
            keep=bool(props.get("keep", False)),
            share_scope=str(props.get("share-scope", "private")),
            preview_base64=props.get("preview"),  # omit in list queries
        )

    _COMMON_PROPS = [
        "uid", "title", "activity", "activity_id", "mime_type",
        "timestamp", "filesize", "description", "tags", "keep", "share-scope",
    ]

    async def get_entry(self, uid: str) -> JournalEntry | None:
        try:
            results, _ = self._ds.find({"uid": uid}, self._COMMON_PROPS + ["preview"])
            if not results:
                return None
            return self._props_to_entry(dict(results[0]))
        except Exception:
            return None

    async def list_entries(self, query: SearchQuery) -> tuple[list[JournalEntry], int]:
        ds_query: dict[str, Any] = {
            "limit": query.limit,
            "offset": query.offset,
            "order_by": [query.order_by],
        }
        if query.query:
            ds_query["query"] = query.query
        if query.activity:
            ds_query["activity"] = query.activity
        if query.mime_type:
            ds_query["mime_type"] = query.mime_type

        results, total = self._ds.find(ds_query, self._COMMON_PROPS)
        entries = [self._props_to_entry(dict(r)) for r in results]

        # Client-side tag filtering (datastore doesn't natively AND-filter tags)
        if query.tags:
            entries = [e for e in entries if all(t in e.tags for t in query.tags)]

        return entries, int(total)

    async def delete_entry(self, uid: str) -> bool:
        try:
            self._ds.delete(uid)
            return True
        except Exception:
            return False


# ---------------------------------------------------------------------------
# File backend (flat JSON files in a directory)
# ---------------------------------------------------------------------------

class FileDatastoreAdapter(BaseDatastoreAdapter):
    """
    Reads journal entries from a directory of JSON files.
    Useful for development on any platform.

    Each file must be a JSON object with keys matching JournalEntry fields.
    The `uid` field is optional; if absent the filename (stem) is used.
    """

    def __init__(self, path: str = settings.datastore_file_path) -> None:
        self.root = Path(path)
        if not self.root.exists():
            self.root.mkdir(parents=True, exist_ok=True)

    def _load_all(self) -> list[JournalEntry]:
        entries: list[JournalEntry] = []
        for fp in self.root.glob("*.json"):
            try:
                data = json.loads(fp.read_text())
                if "uid" not in data:
                    data["uid"] = fp.stem
                if "timestamp" in data and isinstance(data["timestamp"], str):
                    data["timestamp"] = datetime.fromisoformat(data["timestamp"])
                entries.append(JournalEntry(**data))
            except Exception:
                continue
        return entries

    async def get_entry(self, uid: str) -> JournalEntry | None:
        for e in self._load_all():
            if e.uid == uid:
                return e
        return None

    async def list_entries(self, query: SearchQuery) -> tuple[list[JournalEntry], int]:
        entries = self._load_all()

        if query.activity:
            entries = [e for e in entries if e.activity == query.activity]
        if query.mime_type:
            entries = [e for e in entries if e.mime_type.startswith(query.mime_type)]
        if query.tags:
            entries = [e for e in entries if all(t in e.tags for t in query.tags)]
        if query.query:
            q = query.query.lower()
            entries = [
                e for e in entries
                if q in e.title.lower() or q in e.description.lower()
            ]

        reverse = query.order_by.startswith("-")
        field = query.order_by.lstrip("-")
        entries.sort(key=lambda e: getattr(e, field, None) or "", reverse=reverse)

        total = len(entries)
        page = entries[query.offset: query.offset + query.limit]
        return page, total

    async def delete_entry(self, uid: str) -> bool:
        fp = self.root / f"{uid}.json"
        if fp.exists():
            fp.unlink()
            return True
        return False


# ---------------------------------------------------------------------------
# Mock backend (in-memory, for tests)
# ---------------------------------------------------------------------------

_MOCK_ENTRIES: list[JournalEntry] = [
    JournalEntry(
        uid="mock-001",
        title="My first Turtle drawing",
        activity="org.sugarlabs.TurtleArt",
        mime_type="image/png",
        timestamp=datetime(2024, 9, 1, 10, 0, tzinfo=timezone.utc),
        description="I made a spiral using a repeat loop.",
        tags=["art", "loops"],
    ),
    JournalEntry(
        uid="mock-002",
        title="Addition practice",
        activity="org.laptop.Calculate",
        mime_type="text/plain",
        timestamp=datetime(2024, 9, 3, 14, 30, tzinfo=timezone.utc),
        description="Practised adding numbers up to 100.",
        tags=["maths"],
    ),
    JournalEntry(
        uid="mock-003",
        title="Story: The Moon",
        activity="org.laptop.Write",
        mime_type="application/rtf",
        timestamp=datetime(2024, 9, 5, 9, 15, tzinfo=timezone.utc),
        description="Wrote a short story about a journey to the moon.",
        tags=["writing", "science"],
    ),
    JournalEntry(
        uid="mock-004",
        title="Music Blocks composition",
        activity="org.sugarlabs.MusicBlocks",
        mime_type="application/json",
        timestamp=datetime(2024, 9, 7, 11, 0, tzinfo=timezone.utc),
        description="Composed a melody using the pentatonic scale.",
        tags=["music", "art"],
    ),
]


class MockDatastoreAdapter(BaseDatastoreAdapter):
    async def get_entry(self, uid: str) -> JournalEntry | None:
        return next((e for e in _MOCK_ENTRIES if e.uid == uid), None)

    async def list_entries(self, query: SearchQuery) -> tuple[list[JournalEntry], int]:
        entries = list(_MOCK_ENTRIES)
        if query.activity:
            entries = [e for e in entries if e.activity == query.activity]
        if query.mime_type:
            entries = [e for e in entries if e.mime_type.startswith(query.mime_type)]
        if query.tags:
            entries = [e for e in entries if all(t in e.tags for t in query.tags)]
        if query.query:
            q = query.query.lower()
            entries = [
                e for e in entries
                if q in e.title.lower() or q in e.description.lower()
            ]
        reverse = query.order_by.startswith("-")
        field = query.order_by.lstrip("-")
        entries.sort(key=lambda e: getattr(e, field, None) or "", reverse=reverse)
        total = len(entries)
        return entries[query.offset: query.offset + query.limit], total

    async def delete_entry(self, uid: str) -> bool:
        for i, e in enumerate(_MOCK_ENTRIES):
            if e.uid == uid:
                _MOCK_ENTRIES.pop(i)
                return True
        return False


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_datastore_adapter() -> BaseDatastoreAdapter:
    backend = settings.datastore_backend
    if backend == "dbus":
        return DBusDatastoreAdapter()
    if backend == "file":
        return FileDatastoreAdapter()
    return MockDatastoreAdapter()
