"""API 路由汇总"""
from fastapi import APIRouter
from app.api import datasource, health, mock_data, preferences, semantic, sessions

api_router = APIRouter()
api_router.include_router(sessions.router, prefix="/sessions", tags=["会话管理"])
api_router.include_router(semantic.router, prefix="/semantic", tags=["语义建模"])
api_router.include_router(datasource.router, prefix="/datasource", tags=["数据源"])
api_router.include_router(preferences.router, prefix="/preferences", tags=["用户偏好"])
api_router.include_router(mock_data.router, prefix="/mock", tags=["Mock数据"])
api_router.include_router(health.router, tags=["health"])
