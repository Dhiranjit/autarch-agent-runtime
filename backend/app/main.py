"""Main FastAPI application entry point."""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import router as api_router
from app.config import settings
from app.db.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan handler to initialize SQLite tables on startup."""
    await init_db()
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)

# Configure CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API router
app.include_router(api_router)


@app.get("/health")
async def health_check():
    """Service health check with active provider and model info."""
    has_key = bool(settings.openai_api_key)
    return {
        "status": "ok",
        "app": settings.app_name,
        "provider": "openai" if has_key else "mock",
        "model": settings.openai_model if has_key else "deterministic-mock",
    }

