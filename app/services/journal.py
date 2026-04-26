"""
app/services/journal.py — business logic layer.

JournalService      wraps the datastore adapter with query / aggregation helpers.
ReflectionService   builds prompts and calls the LLM adapter.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

from app.adapters.datastore import BaseDatastoreAdapter
from app.adapters.llm import BaseLLMAdapter
from app.models.journal import (
    InsightsResponse,
    JournalEntry,
    JournalEntryBrief,
    ReflectRequest,
    ReflectResponse,
    SearchQuery,
)


# ---------------------------------------------------------------------------
# JournalService
# ---------------------------------------------------------------------------

class JournalService:
    def __init__(self, adapter: BaseDatastoreAdapter) -> None:
        self._ds = adapter

    async def get_entry(self, uid: str) -> JournalEntry | None:
        return await self._ds.get_entry(uid)

    async def list_entries(
        self, query: SearchQuery
    ) -> tuple[list[JournalEntryBrief], int]:
        entries, total = await self._ds.list_entries(query)
        briefs = [
            JournalEntryBrief(
                uid=e.uid,
                title=e.title,
                activity=e.activity,
                mime_type=e.mime_type,
                timestamp=e.timestamp,
                tags=e.tags,
                keep=e.keep,
            )
            for e in entries
        ]
        return briefs, total

    async def delete_entry(self, uid: str) -> bool:
        return await self._ds.delete_entry(uid)

    async def aggregate(
        self,
        activity: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> dict:
        """Return aggregate stats over a (filtered) view of the journal."""
        all_entries, _ = await self._ds.list_entries(
            SearchQuery(limit=200, offset=0, activity=activity)
        )
        if since:
            all_entries = [e for e in all_entries if e.timestamp and e.timestamp >= since]
        if until:
            all_entries = [e for e in all_entries if e.timestamp and e.timestamp <= until]

        days: set[str] = set()
        activity_counter: Counter = Counter()
        tag_counter: Counter = Counter()

        for e in all_entries:
            if e.timestamp:
                days.add(e.timestamp.date().isoformat())
            if e.activity:
                activity_counter[e.activity] += 1
            for t in e.tags:
                tag_counter[t] += 1

        return {
            "entries": all_entries,
            "total": len(all_entries),
            "active_days": len(days),
            "top_activities": [
                {"activity": a, "count": c}
                for a, c in activity_counter.most_common(10)
            ],
            "top_tags": [
                {"tag": t, "count": c} for t, c in tag_counter.most_common(10)
            ],
        }


# ---------------------------------------------------------------------------
# ReflectionService
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a thoughtful educational assistant helping young learners reflect on \
their work saved in the Sugar Learning Platform Journal. \
Your reflections are encouraging, age-appropriate, and focused on what the \
learner can think about or try next. \
Keep responses concise (3-5 paragraphs) unless asked otherwise. \
Do not include markdown headers."""


def _entry_to_text(entry: JournalEntry) -> str:
    parts = [
        f"Title: {entry.title}",
        f"Activity: {entry.activity}",
        f"Created: {entry.timestamp.isoformat() if entry.timestamp else 'unknown'}",
    ]
    if entry.description:
        parts.append(f"Description: {entry.description}")
    if entry.tags:
        parts.append(f"Tags: {', '.join(entry.tags)}")
    return "\n".join(parts)


class ReflectionService:
    def __init__(
        self, journal: JournalService, llm: BaseLLMAdapter
    ) -> None:
        self._journal = journal
        self._llm = llm

    async def reflect(self, req: ReflectRequest) -> ReflectResponse:
        entries = []
        for uid in req.uids:
            e = await self._journal.get_entry(uid)
            if e:
                entries.append(e)

        if not entries:
            raise ValueError("None of the requested entry UIDs were found.")

        entry_texts = "\n\n---\n\n".join(_entry_to_text(e) for e in entries)

        user_msg = (
            f"Here are the journal entries to reflect on:\n\n{entry_texts}"
        )
        if req.prompt_hint:
            user_msg += f"\n\nAdditional instruction: {req.prompt_hint}"
        if req.language != "en":
            user_msg += f"\n\nPlease respond in language: {req.language}."

        reflection = await self._llm.complete(system=_SYSTEM_PROMPT, user=user_msg)

        return ReflectResponse(
            uids=req.uids,
            reflection=reflection,
            model_used=self._llm.model_name,
        )

    async def insights(
        self,
        activity: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> InsightsResponse:
        agg = await self._journal.aggregate(activity=activity, since=since, until=until)

        # Build a summary the LLM can narrate
        entry_sample = agg["entries"][:10]  # cap to avoid huge prompts
        sample_text = "\n".join(
            f"- {_entry_to_text(e)}" for e in entry_sample
        )
        stats_text = (
            f"Total entries: {agg['total']}\n"
            f"Active days: {agg['active_days']}\n"
            f"Top activities: {agg['top_activities']}\n"
            f"Top tags: {agg['top_tags']}\n"
        )
        user_msg = (
            "Here is an overview of a learner's Sugar Journal.\n\n"
            f"Statistics:\n{stats_text}\n"
            f"Sample entries (up to 10):\n{sample_text}\n\n"
            "Write a short, encouraging narrative (2-3 paragraphs) summarising "
            "this learner's progress, patterns, and one concrete suggestion for "
            "what to explore next."
        )

        narrative = await self._llm.complete(system=_SYSTEM_PROMPT, user=user_msg)

        return InsightsResponse(
            total_entries=agg["total"],
            active_days=agg["active_days"],
            top_activities=agg["top_activities"],
            top_tags=agg["top_tags"],
            narrative=narrative,
            model_used=self._llm.model_name,
        )
