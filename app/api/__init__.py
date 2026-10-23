"""API package."""
from app.api.routers import comparisons_router, manuals_router, selections_router

__all__ = [
    "manuals_router",
    "comparisons_router",
    "selections_router",
]
