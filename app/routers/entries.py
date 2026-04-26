"""
app/routers/entries.py — CRUD + search endpoints for Journal entries.

GET  /entries            — paginated list
GET  /entries/{uid}      — single entry with preview
POST /entries/search     — filtered search
DELETE /entries/{uid}    — remove an entry
"""
from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies import get_journal_service
from app.models.journal import JournalEntry, JournalEntryBrief, SearchQuery
from app.services.journal import JournalService

router = APIRouter(prefix="/entries", tags=["entries"])


@router.get("", response_model=dict)
async def list_entries(
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    order_by: str = Query("-timestamp"),
    svc: JournalService = Depends(get_journal_service),
):
    """Return a paginated list of journal entries (lightweight view)."""
    q = SearchQuery(limit=limit, offset=offset, order_by=order_by)
    entries, total = await svc.list_entries(q)
    return {"total": total, "offset": offset, "limit": limit, "entries": entries}


@router.get("/{uid}", response_model=JournalEntry)
async def get_entry(
    uid: str,
    svc: JournalService = Depends(get_journal_service),
):
    """Return full details for a single entry (includes preview thumbnail)."""
    entry = await svc.get_entry(uid)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Entry {uid!r} not found")
    return entry


@router.post("/search", response_model=dict)
async def search_entries(
    body: SearchQuery,
    svc: JournalService = Depends(get_journal_service),
):
    """Full-text + metadata search across journal entries."""
    entries, total = await svc.list_entries(body)
    return {
        "total": total,
        "offset": body.offset,
        "limit": body.limit,
        "entries": entries,
    }


@router.post("", response_model=JournalEntry, status_code=201)
async def save_entry(
    body: JournalEntry,
    svc: JournalService = Depends(get_journal_service),
):
    """
    Save a new journal entry.
    Broadcasts a live WebSocket event to all connected clients.
    """
    saved = await svc.save_entry(body)
    return saved


@router.delete("/{uid}", response_model=dict)
async def delete_entry(
    uid: str,
    svc: JournalService = Depends(get_journal_service),
):
    """Delete a journal entry from the datastore."""
    deleted = await svc.delete_entry(uid)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Entry {uid!r} not found")
    return {"deleted": uid}
