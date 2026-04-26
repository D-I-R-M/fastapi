#!/usr/bin/env python3
"""
tools/mock_datastore_service.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
A real D-Bus service that registers as org.laptop.sugar.DataStore on the
session bus and serves the sample_journal JSON files.

This lets you develop and test DBusDatastoreAdapter without a running Sugar
session. When you eventually run Sugar, switch DATASTORE_BACKEND=dbus and
point it at the real datastore — your adapter code stays identical.

Interface implemented
---------------------
Exactly mirrors sugar-datastore's org.laptop.sugar.DataStore interface:

  find(query: dict, properties: list[str]) -> (list[dict], uint32)
  delete(uid: str) -> void
  get_filename(uid: str) -> str          [returns empty string in mock]
  save(props: dict, filedata: bytes, ...) -> str   [stub — returns new uid]

Signal emitted
--------------
  Updated(uid: str, event: str)   — on delete / save

Usage
-----
  # Terminal 1 — start the mock service
  python tools/mock_datastore_service.py

  # Terminal 2 — run the FastAPI app pointed at the mock bus
  DATASTORE_BACKEND=dbus uvicorn app.main:app --reload

Requirements
------------
  pip install dbus-python pygobject   (Linux only)
  On Ubuntu/Debian: sudo apt install python3-dbus python3-gi
"""

import json
import logging
import os
import signal
import sys
import time
import uuid
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger("mock-datastore")

# ---------------------------------------------------------------------------
# Guard: dbus-python is Linux-only
# ---------------------------------------------------------------------------
try:
    import dbus
    import dbus.service
    import dbus.mainloop.glib
    from gi.repository import GLib  # type: ignore
except ImportError:
    sys.exit(
        "ERROR: dbus-python / pygobject not available.\n"
        "Install with: sudo apt install python3-dbus python3-gi\n"
        "This script only works on Linux."
    )

# ---------------------------------------------------------------------------
# Constants — must match the real sugar-datastore exactly
# ---------------------------------------------------------------------------
DS_SERVICE   = "org.laptop.sugar.DataStore"
DS_PATH      = "/org/laptop/sugar/DataStore"
DS_INTERFACE = "org.laptop.sugar.DataStore"

SAMPLE_DIR = Path(__file__).parent.parent / "sample_journal"

# ---------------------------------------------------------------------------
# In-memory store (loaded from sample_journal/*.json at startup)
# ---------------------------------------------------------------------------

def _load_samples() -> dict[str, dict]:
    """Load sample JSON files into memory. Key = uid."""
    store: dict[str, dict] = {}
    for fp in sorted(SAMPLE_DIR.glob("*.json")):
        try:
            data = json.loads(fp.read_text())
            uid = data.get("uid") or fp.stem
            data["uid"] = uid

            # Normalise timestamp → Unix epoch string (what the real DS sends)
            ts = data.get("timestamp", "")
            if ts and not ts.replace(".", "").isdigit():
                from datetime import datetime, timezone
                try:
                    dt = datetime.fromisoformat(ts)
                    data["timestamp"] = str(dt.timestamp())
                except ValueError:
                    data["timestamp"] = ""

            # Normalise tags → comma-separated string (real DS format)
            if isinstance(data.get("tags"), list):
                data["tags"] = ",".join(data["tags"])

            # Normalise keep → "1"/"0"
            data["keep"] = "1" if data.get("keep") else "0"

            store[uid] = data
            log.info("Loaded entry: %s — %s", uid, data.get("title", "?"))
        except Exception as exc:
            log.warning("Skipping %s: %s", fp.name, exc)
    return store


# ---------------------------------------------------------------------------
# D-Bus service class
# ---------------------------------------------------------------------------

class MockDataStore(dbus.service.Object):
    """
    Implements org.laptop.sugar.DataStore on the session bus.

    Only the methods actually used by DBusDatastoreAdapter (and jarabe/journal)
    are implemented. Everything else raises NotImplemented.
    """

    def __init__(self, bus: dbus.SessionBus) -> None:
        bus_name = dbus.service.BusName(DS_SERVICE, bus=bus)
        super().__init__(bus_name, DS_PATH)
        self._store = _load_samples()
        log.info("MockDataStore ready on %s — %d entries", DS_SERVICE, len(self._store))

    # ------------------------------------------------------------------
    # find(query, properties) -> (entries, count)
    #
    # Real signature (from sugar-datastore/src/carquinyol/datastore.py):
    #   find(query: a{sv}, properties: as) -> (aa{sv}, u)
    # ------------------------------------------------------------------

    @dbus.service.method(
        dbus_interface=DS_INTERFACE,
        in_signature="a{sv}as",
        out_signature="aa{sv}u",
    )
    def find(self, query: dbus.Dictionary, properties: dbus.Array):
        log.info("find() query=%s props=%s", dict(query), list(properties))

        entries = list(self._store.values())

        # --- filter ---
        q_uid      = str(query.get("uid", ""))
        q_activity = str(query.get("activity", ""))
        q_mime     = str(query.get("mime_type", ""))
        q_text     = str(query.get("query", "")).lower()

        if q_uid:
            entries = [e for e in entries if e.get("uid") == q_uid]
        if q_activity:
            entries = [e for e in entries if e.get("activity") == q_activity]
        if q_mime:
            entries = [e for e in entries if e.get("mime_type", "").startswith(q_mime)]
        if q_text:
            entries = [
                e for e in entries
                if q_text in e.get("title", "").lower()
                or q_text in e.get("description", "").lower()
            ]

        # --- sort ---
        order_by_list = query.get("order_by", dbus.Array([], signature="s"))
        order_field = str(order_by_list[0]) if order_by_list else "-timestamp"
        reverse = order_field.startswith("-")
        field = order_field.lstrip("-")
        entries.sort(key=lambda e: e.get(field, "") or "", reverse=reverse)

        total = len(entries)

        # --- paginate ---
        offset = int(query.get("offset", 0))
        limit  = int(query.get("limit", 20))
        page   = entries[offset: offset + limit]

        # --- project properties ---
        props_list = [str(p) for p in properties]
        result = []
        for entry in page:
            if props_list:
                projected = {k: str(v) for k, v in entry.items() if k in props_list}
            else:
                projected = {k: str(v) for k, v in entry.items()}
            result.append(dbus.Dictionary(projected, signature="sv"))

        log.info("find() -> %d/%d entries", len(result), total)
        return dbus.Array(result, signature="a{sv}"), dbus.UInt32(total)

    # ------------------------------------------------------------------
    # delete(uid)
    # ------------------------------------------------------------------

    @dbus.service.method(
        dbus_interface=DS_INTERFACE,
        in_signature="s",
        out_signature="",
    )
    def delete(self, uid: str) -> None:
        uid = str(uid)
        if uid in self._store:
            del self._store[uid]
            log.info("delete() uid=%s — ok", uid)
            self.Updated(uid, "delete")
        else:
            log.warning("delete() uid=%s — not found", uid)
            raise dbus.DBusException(
                f"Entry {uid!r} not found",
                name="org.laptop.sugar.DataStore.NotFound",
            )

    # ------------------------------------------------------------------
    # get_filename(uid) -> str
    # Returns empty string in mock (no actual files on disk)
    # ------------------------------------------------------------------

    @dbus.service.method(
        dbus_interface=DS_INTERFACE,
        in_signature="s",
        out_signature="s",
    )
    def get_filename(self, uid: str) -> str:
        uid = str(uid)
        if uid not in self._store:
            raise dbus.DBusException(
                f"Entry {uid!r} not found",
                name="org.laptop.sugar.DataStore.NotFound",
            )
        return ""   # mock has no backing files

    # ------------------------------------------------------------------
    # save(props, filedata, transfer_ownership) -> uid
    # Stub — stores props in memory, ignores file content
    # ------------------------------------------------------------------

    @dbus.service.method(
        dbus_interface=DS_INTERFACE,
        in_signature="a{sv}sba{sv}",
        out_signature="s",
        async_callbacks=("return_cb", "error_cb"),
    )
    def save(self, props, filedata, transfer_ownership, metadata,
             return_cb, error_cb):
        try:
            props_dict = {str(k): str(v) for k, v in props.items()}
            uid = props_dict.get("uid") or str(uuid.uuid4())
            props_dict["uid"] = uid
            self._store[uid] = props_dict
            log.info("save() uid=%s title=%s", uid, props_dict.get("title", "?"))
            self.Updated(uid, "save")
            return_cb(uid)
        except Exception as exc:
            error_cb(exc)

    # ------------------------------------------------------------------
    # Signal: Updated(uid, event)
    # ------------------------------------------------------------------

    @dbus.service.signal(dbus_interface=DS_INTERFACE, signature="ss")
    def Updated(self, uid: str, event: str) -> None:  # noqa: N802
        log.info("signal Updated uid=%s event=%s", uid, event)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

    try:
        bus = dbus.SessionBus()
    except dbus.DBusException as exc:
        sys.exit(
            f"ERROR: Cannot connect to session D-Bus: {exc}\n"
            "If running outside a desktop session, try:\n"
            "  eval $(dbus-launch --sh-syntax)\n"
            "  python tools/mock_datastore_service.py"
        )

    _service = MockDataStore(bus)  # noqa: F841  — keep reference alive

    loop = GLib.MainLoop()

    def _on_sigint(*_):
        log.info("Shutting down mock datastore…")
        loop.quit()

    signal.signal(signal.SIGINT, _on_sigint)
    signal.signal(signal.SIGTERM, _on_sigint)

    log.info("Mock DataStore running. Press Ctrl-C to stop.")
    loop.run()


if __name__ == "__main__":
    main()
