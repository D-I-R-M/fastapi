from __future__ import annotations

from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field


class JournalEntry(BaseModel):
    uid: str = Field(..., description="Unique object id from the datastore")
    title: str = Field("Untitled", description="Human-readable title")
    activity: str = Field("", description="Bundle id of the activity")
    activity_id: str = Field("", description="Instance id of the activity session")
    mime_type: str = Field("", description="MIME type of the stored file")
    timestamp: datetime | None = Field(None, description="Creation time (UTC)")
    filesize: int = Field(0, description="Size of the stored file in bytes")
    description: str = Field("", description="Free-text description")
    tags: list[str] = Field(default_factory=list, description="User-assigned tags")
    keep: bool = Field(False, description="Whether the entry is starred")
    share_scope: str = Field("private", description="Sharing scope")
    preview_base64: str | None = Field(None, description="Base64 PNG thumbnail")
    extra: dict[str, Any] = Field(default_factory=dict)


class JournalEntryBrief(BaseModel):
    uid: str
    title: str
    activity: str
    mime_type: str
    timestamp: datetime | None
    tags: list[str]
    keep: bool


class SearchQuery(BaseModel):
    query: str = Field("", description="Full-text search term")
    activity: str | None = Field(None, description="Filter by bundle id")
    mime_type: str | None = Field(None, description="Filter by MIME type prefix")
    tags: list[str] = Field(default_factory=list, description="Filter by tags")
    limit: int = Field(20, ge=1, le=200)
    offset: int = Field(0, ge=0)
    order_by: str = Field("-timestamp", description="Sort field")


class ReflectRequest(BaseModel):
    uids: list[str] = Field(..., min_length=1)
    prompt_hint: str = Field("")
    language: str = Field("en")


class ReflectResponse(BaseModel):
    uids: list[str]
    reflection: str
    model_used: str


class InsightsRequest(BaseModel):
    activity: str | None = None
    since: datetime | None = None
    until: datetime | None = None


class InsightsResponse(BaseModel):
    total_entries: int
    active_days: int
    top_activities: list[dict[str, Any]]
    top_tags: list[dict[str, Any]]
    narrative: str
    model_used: str
