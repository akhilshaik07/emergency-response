"""FastAPI application entrypoint for Emergency Response Platform."""

import os
from pathlib import Path
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.openapi.docs import get_swagger_ui_html
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.core.config import settings
from app.core.db import get_db

app = FastAPI(
    title="Community Emergency Response Platform API",
    version="1.0.0",
    description="Emergency Response Platform REST API & Real-time Dispatch Hub",
    docs_url=None,  # Disables default remote CDN docs
    redoc_url=None,
)

# Mount local offline static assets
STATIC_DIR = Path(__file__).resolve().parent / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    """Serve Swagger UI locally with 0 external CDN dependencies."""
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=f"{app.title} - Documentation",
        swagger_js_url="/static/swagger/swagger-ui-bundle.js",
        swagger_css_url="/static/swagger/swagger-ui.css",
        swagger_favicon_url="/static/swagger/favicon-32x32.png",
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


# Include domain routers
from app.api.routes.auth import router as auth_router
from app.api.routes.users import router as users_router
from app.api.routes.societies import router as societies_router

app.include_router(auth_router)
app.include_router(users_router)
app.include_router(societies_router)
