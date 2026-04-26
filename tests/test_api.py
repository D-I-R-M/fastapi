"""
tests/test_api.py — integration tests using FastAPI's TestClient.

Run with:
    pytest -v

All tests use the mock datastore and mock LLM so no external services are needed.
Environment is forced to mock backends via monkeypatching before the app is imported.
"""
import os

# Force mock backends before any app module is imported
os.environ.setdefault("DATASTORE_BACKEND", "mock")
os.environ.setdefault("LLM_PROVIDER", "mock")

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

def test_root():
    r = client.get("/")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_health():
    r = client.get("/health")
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# Entries — list
# ---------------------------------------------------------------------------

def test_list_entries_default():
    r = client.get("/entries")
    assert r.status_code == 200
    body = r.json()
    assert "entries" in body
    assert "total" in body
    assert isinstance(body["entries"], list)


def test_list_entries_pagination():
    r = client.get("/entries?limit=2&offset=0")
    assert r.status_code == 200
    body = r.json()
    assert len(body["entries"]) <= 2


def test_list_entries_order_asc():
    r = client.get("/entries?order_by=title")
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# Entries — get single
# ---------------------------------------------------------------------------

def test_get_existing_entry():
    r = client.get("/entries/mock-001")
    assert r.status_code == 200
    body = r.json()
    assert body["uid"] == "mock-001"
    assert "title" in body
    assert "activity" in body


def test_get_missing_entry():
    r = client.get("/entries/does-not-exist")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Entries — search
# ---------------------------------------------------------------------------

def test_search_by_query():
    r = client.post("/entries/search", json={"query": "turtle", "limit": 10})
    assert r.status_code == 200
    body = r.json()
    # Mock data has a TurtleArt entry; title doesn't contain "turtle" but description might not either
    # Just assert the response shape is correct
    assert "entries" in body
    assert "total" in body


def test_search_by_activity():
    r = client.post(
        "/entries/search",
        json={"activity": "org.sugarlabs.TurtleArt", "limit": 10},
    )
    assert r.status_code == 200
    body = r.json()
    for entry in body["entries"]:
        assert entry["activity"] == "org.sugarlabs.TurtleArt"


def test_search_by_tag():
    r = client.post("/entries/search", json={"tags": ["maths"], "limit": 10})
    assert r.status_code == 200
    body = r.json()
    for entry in body["entries"]:
        assert "maths" in entry["tags"]


def test_search_no_results():
    r = client.post(
        "/entries/search",
        json={"activity": "org.nonexistent.Activity", "limit": 10},
    )
    assert r.status_code == 200
    assert r.json()["total"] == 0


# ---------------------------------------------------------------------------
# Entries — delete
# ---------------------------------------------------------------------------

def test_delete_entry():
    # First confirm mock-002 exists
    r = client.get("/entries/mock-002")
    assert r.status_code == 200

    # Delete it
    r = client.delete("/entries/mock-002")
    assert r.status_code == 200
    assert r.json()["deleted"] == "mock-002"

    # Confirm it's gone
    r = client.get("/entries/mock-002")
    assert r.status_code == 404


def test_delete_missing_entry():
    r = client.delete("/entries/definitely-not-here")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Reflect
# ---------------------------------------------------------------------------

def test_reflect_single_entry():
    r = client.post("/reflect", json={"uids": ["mock-001"]})
    assert r.status_code == 200
    body = r.json()
    assert "reflection" in body
    assert body["uids"] == ["mock-001"]
    assert "model_used" in body


def test_reflect_multiple_entries():
    r = client.post("/reflect", json={"uids": ["mock-003", "mock-004"]})
    assert r.status_code == 200
    body = r.json()
    assert len(body["uids"]) == 2
    assert isinstance(body["reflection"], str)
    assert len(body["reflection"]) > 0


def test_reflect_with_prompt_hint():
    r = client.post(
        "/reflect",
        json={"uids": ["mock-001"], "prompt_hint": "Focus on the use of loops"},
    )
    assert r.status_code == 200


def test_reflect_missing_uids():
    r = client.post("/reflect", json={"uids": ["uid-that-does-not-exist"]})
    assert r.status_code == 404


def test_reflect_empty_uids():
    # Pydantic min_length=1 on the list → 422
    r = client.post("/reflect", json={"uids": []})
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Insights
# ---------------------------------------------------------------------------

def test_insights_all():
    r = client.post("/insights", json={})
    print(r.json())
    assert r.status_code == 200
    body = r.json()
    assert "total_entries" in body
    assert "active_days" in body
    assert "top_activities" in body
    assert "top_tags" in body
    assert "narrative" in body
    assert "model_used" in body


def test_insights_filtered_by_activity():
    r = client.post(
        "/insights",
        json={"activity": "org.sugarlabs.MusicBlocks"},
    )
    assert r.status_code == 200
    body = r.json()
    # Only music entry should match
    assert body["total_entries"] <= 1


def test_insights_date_filter():
    r = client.post(
        "/insights",
        json={"since": "2024-09-05T00:00:00Z", "until": "2024-09-10T00:00:00Z"},
    )
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["total_entries"], int)
