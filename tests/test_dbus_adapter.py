"""
tests/test_dbus_adapter.py
~~~~~~~~~~~~~~~~~~~~~~~~~~
Integration tests for DBusDatastoreAdapter against mock_datastore_service.py.

These tests require:
  - Linux with dbus-python and python3-gi installed
  - The mock service running (or we spawn it in-process for CI)

Run only these tests:
  pytest tests/test_dbus_adapter.py -v

Skip on non-Linux / missing dbus:
  pytest tests/test_dbus_adapter.py -v  (auto-skipped if dbus unavailable)

How it works
------------
1. We import MockDataStore directly and register it on a private session bus.
2. We instantiate DBusDatastoreAdapter pointed at that same bus.
3. We exercise every public method and assert correctness.

This catches:
  - D-Bus type mismatches (UInt32 vs int, Array vs list, etc.)
  - Async executor wrapping correctness
  - Query filtering logic in the mock service
  - Error paths (delete unknown uid, get unknown uid)
"""

import asyncio
import os
import sys
import pytest

# ---------------------------------------------------------------------------
# Skip the entire module if dbus is not available (non-Linux, no dbus-python)
# ---------------------------------------------------------------------------
dbus_available = False
try:
    import dbus
    import dbus.mainloop.glib
    from gi.repository import GLib  # type: ignore
    dbus_available = True
except ImportError:
    pass

pytestmark = pytest.mark.skipif(
    not dbus_available,
    reason="dbus-python / pygobject not installed — skipping D-Bus tests",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def dbus_session():
    """
    Ensure a D-Bus session bus is available.
    Returns the bus address string.
    """
    addr = os.environ.get("DBUS_SESSION_BUS_ADDRESS", "")
    if not addr:
        pytest.skip(
            "No DBUS_SESSION_BUS_ADDRESS set.\n"
            "Run: eval $(dbus-launch --sh-syntax) before pytest,\n"
            "or start tools/run_dbus_mock.sh in another terminal."
        )
    return addr


@pytest.fixture(scope="module")
def mock_service(dbus_session):
    """
    Register the MockDataStore service on the session bus.
    Tears down after all tests in this module complete.
    """
    # Import here so the skip above fires before import errors
    import dbus.mainloop.glib
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

    # Inline import of the mock service class
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))
    from tools.mock_datastore_service import MockDataStore

    bus = dbus.SessionBus()

    # Check if the service is already running (e.g. user started run_dbus_mock.sh)
    try:
        existing = bus.get_object(
            "org.laptop.sugar.DataStore",
            "/org/laptop/sugar/DataStore",
        )
        iface = dbus.Interface(existing, dbus_interface="org.laptop.sugar.DataStore")
        iface.find({}, [])   # probe
        # Already running — don't register a second one
        yield bus
        return
    except Exception:
        pass

    # Not running — register in this process
    service = MockDataStore(bus)
    yield bus
    # GLib loop not started here; synchronous D-Bus calls still work


@pytest.fixture
def adapter(mock_service):
    """Return a DBusDatastoreAdapter connected to the mock service."""
    # Force dbus backend
    import os
    os.environ["DATASTORE_BACKEND"] = "dbus"

    from app.adapters.datastore import DBusDatastoreAdapter
    return DBusDatastoreAdapter()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def run(coro):
    """Run a coroutine synchronously in tests."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDBusFind:
    def test_list_all_returns_entries(self, adapter):
        from app.models.journal import SearchQuery
        entries, total = run(adapter.list_entries(SearchQuery()))
        assert total >= 1
        assert len(entries) >= 1

    def test_list_respects_limit(self, adapter):
        from app.models.journal import SearchQuery
        entries, total = run(adapter.list_entries(SearchQuery(limit=2)))
        assert len(entries) <= 2
        assert total >= len(entries)

    def test_list_respects_offset(self, adapter):
        from app.models.journal import SearchQuery
        all_entries, total = run(adapter.list_entries(SearchQuery(limit=100)))
        if total < 2:
            pytest.skip("Need at least 2 entries for offset test")
        page2, _ = run(adapter.list_entries(SearchQuery(limit=1, offset=1)))
        assert page2[0].uid != all_entries[0].uid

    def test_filter_by_activity(self, adapter):
        from app.models.journal import SearchQuery
        entries, _ = run(
            adapter.list_entries(SearchQuery(activity="org.sugarlabs.TurtleArt"))
        )
        for e in entries:
            assert e.activity == "org.sugarlabs.TurtleArt"

    def test_filter_by_mime_type(self, adapter):
        from app.models.journal import SearchQuery
        entries, _ = run(adapter.list_entries(SearchQuery(mime_type="image/")))
        for e in entries:
            assert e.mime_type.startswith("image/")

    def test_filter_by_text_query(self, adapter):
        from app.models.journal import SearchQuery
        entries, _ = run(adapter.list_entries(SearchQuery(query="spiral")))
        # At least one entry description mentions spiral (sample-001)
        assert any("spiral" in (e.description or "").lower() for e in entries)

    def test_sort_descending_timestamp(self, adapter):
        from app.models.journal import SearchQuery
        entries, _ = run(adapter.list_entries(SearchQuery(order_by="-timestamp", limit=50)))
        timestamps = [e.timestamp for e in entries if e.timestamp]
        assert timestamps == sorted(timestamps, reverse=True)

    def test_entry_fields_populated(self, adapter):
        from app.models.journal import SearchQuery
        entries, _ = run(adapter.list_entries(SearchQuery(limit=1)))
        assert entries, "Expected at least one entry"
        e = entries[0]
        assert e.uid
        assert isinstance(e.tags, list)
        assert isinstance(e.keep, bool)


class TestDBusGetEntry:
    def test_get_known_entry(self, adapter):
        from app.models.journal import SearchQuery
        # Get the uid of the first available entry
        entries, _ = run(adapter.list_entries(SearchQuery(limit=1)))
        assert entries
        uid = entries[0].uid

        entry = run(adapter.get_entry(uid))
        assert entry is not None
        assert entry.uid == uid

    def test_get_unknown_entry_returns_none(self, adapter):
        entry = run(adapter.get_entry("uid-that-does-not-exist-xyz"))
        assert entry is None

    def test_get_entry_includes_all_fields(self, adapter):
        from app.models.journal import SearchQuery
        entries, _ = run(adapter.list_entries(SearchQuery(limit=1)))
        uid = entries[0].uid
        entry = run(adapter.get_entry(uid))
        assert entry.title is not None
        assert entry.activity is not None
        assert entry.mime_type is not None


class TestDBusDelete:
    def test_delete_existing_entry(self, adapter):
        from app.models.journal import SearchQuery
        entries, total_before = run(adapter.list_entries(SearchQuery(limit=100)))
        if not entries:
            pytest.skip("No entries to delete")

        # Pick the last one so we don't disturb other tests
        uid = entries[-1].uid
        deleted = run(adapter.delete_entry(uid))
        assert deleted is True

        # Confirm it's gone
        entry = run(adapter.get_entry(uid))
        assert entry is None

        _, total_after = run(adapter.list_entries(SearchQuery(limit=100)))
        assert total_after == total_before - 1

    def test_delete_unknown_entry_returns_false(self, adapter):
        result = run(adapter.delete_entry("nonexistent-uid-abc"))
        assert result is False


class TestDBusTagFiltering:
    def test_tag_filter_client_side(self, adapter):
        """Tags are AND-filtered client-side since the datastore doesn't support it."""
        from app.models.journal import SearchQuery
        entries, _ = run(adapter.list_entries(SearchQuery(tags=["art"], limit=50)))
        for e in entries:
            assert "art" in e.tags
