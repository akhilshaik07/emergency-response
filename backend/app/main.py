"""FastAPI application entrypoint for Emergency Response Platform."""

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.core.config import settings
from app.core.db import get_db

app = FastAPI(
    title="Community Emergency Response Platform API",
    version="1.0.0",
    description="Emergency Response Platform REST API & Real-time Dispatch Hub",
)

# Configure CORS Middleware using explicit origin list from settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["Health"])
async def health_check():
    """Basic web server liveness check (does not touch DB)."""
    return {"status": "ok"}


@app.get("/health/db", tags=["Health"])
async def health_db_check(db: AsyncSession = Depends(get_db)):
    """Database connectivity health check."""
    result = await db.execute(text("SELECT 1"))
    val = result.scalar()
    if val == 1:
        return {"status": "ok", "db": "connected"}
    return {"status": "error", "db": "unhealthy"}
