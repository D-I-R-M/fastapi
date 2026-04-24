"""
app/main.py — FastAPI application factory for the Sugar Journal backend.

Run with:
    uvicorn app.main:app --reload

Interactive docs available at:
    http://localhost:8000/docs   (Swagger UI)
    http://localhost:8000/redoc
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import entries, reflection

app = FastAPI(
    title="Sugar Journal AI API",
    description=(
        "FastAPI backend that exposes the Sugar Learning Platform Journal "
        "(jarabe/journal + sugar-datastore) over HTTP, with AI-powered "
        "reflection and learning-insights endpoints."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — open by default for development; tighten in production via CORS_ORIGINS env
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(entries.router)
app.include_router(reflection.router)


@app.get("/", tags=["health"])
async def root():
    return {
        "service": "Sugar Journal AI API",
        "status": "ok",
        "docs": "/docs",
    }


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok"}
