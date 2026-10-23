"""
FastAPI Application Entry Point.

Configures:
- Application lifecycle and database initialization
- CORS middleware
- Health check endpoint
- Routers for manuals, comparisons, and selections
- Global clean exception handling
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, Dict

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routers import comparisons_router, manuals_router, selections_router
from app.api.schemas import HealthResponse
from app.db.session import init_db

logger = logging.getLogger("ct200_qa_api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initializes database schema on application startup."""
    try:
        init_db()
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize database on startup: {e}")
    yield


app = FastAPI(
    title="CardioTrack CT-200 Technical Documentation QA API",
    description="REST API for parsing, comparing, and persisting CT-200 manual documentation across revisions.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Enable CORS for frontend/dashboard development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["Health"],
    summary="Application Health Check",
)
def health_check() -> HealthResponse:
    """Returns application health status, name, and version."""
    return HealthResponse(status="ok", app="ct200-qa", version="1.0.0")


# Include module routers
app.include_router(manuals_router)
app.include_router(comparisons_router)
app.include_router(selections_router)


# Global exception handler for uncaught server errors
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catches unexpected exceptions to prevent leaking internal stack traces."""
    # Don't intercept HTTPExceptions
    if isinstance(exc, HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )

    logger.error(f"Unhandled error processing {request.method} {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal server error occurred while processing the request."},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
