"""
app/routers/reflection.py — AI reflection and learning-insights endpoints.

POST /reflect    — reflect on one or more specific entries
POST /insights   — aggregate narrative + stats across the journal
"""
from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_reflection_service
from app.models.journal import InsightsRequest, InsightsResponse, ReflectRequest, ReflectResponse
from app.services.journal import ReflectionService

router = APIRouter(tags=["reflection"])


@router.post("/reflect", response_model=ReflectResponse)
async def reflect(
    body: ReflectRequest,
    svc: ReflectionService = Depends(get_reflection_service),
):
    """
    Ask the LLM to reflect on one or more journal entries.

    Supply the UIDs of the entries and an optional prompt hint to guide
    the style or focus of the reflection.
    """
    try:
        return await svc.reflect(body)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"LLM error: {exc}") from exc


@router.post("/insights", response_model=InsightsResponse)
async def insights(
    body: InsightsRequest,
    svc: ReflectionService = Depends(get_reflection_service),
):
    """
    Generate aggregate insights across the whole journal (or a filtered slice).

    Returns statistics (entry count, active days, top activities/tags) plus
    an LLM-generated narrative about the learner's progress.
    """
    try:
        return await svc.insights(
            activity=body.activity,
            since=body.since,
            until=body.until,
        )
    except Exception as exc:
        import traceback
        raise HTTPException(status_code=502, detail=f"LLM error: {exc}") from exc
