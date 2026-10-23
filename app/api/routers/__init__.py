"""API Routers package."""
from app.api.routers.comparisons import router as comparisons_router
from app.api.routers.manuals import router as manuals_router
from app.api.routers.selections import router as selections_router

__all__ = [
    "manuals_router",
    "comparisons_router",
    "selections_router",
]
