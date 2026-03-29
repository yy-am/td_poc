"""API route aggregation."""

from fastapi import APIRouter

from app.api import datasource, health, mock_data_v2, preferences, semantic_v2, sessions

api_router = APIRouter()
api_router.include_router(sessions.router, prefix="/sessions", tags=["sessions"])
api_router.include_router(semantic_v2.router, prefix="/semantic", tags=["semantic"])
api_router.include_router(datasource.router, prefix="/datasource", tags=["datasource"])
api_router.include_router(preferences.router, prefix="/preferences", tags=["preferences"])
api_router.include_router(mock_data_v2.router, prefix="/mock", tags=["mock"])
api_router.include_router(health.router, tags=["health"])
