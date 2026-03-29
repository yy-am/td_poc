"""FastAPI 应用入口"""
import os
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# 确保从项目根目录导入
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import get_settings
from app.database import init_database, close_database

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    await init_database()
    yield
    await close_database()


app = FastAPI(
    title="TDA-TDP 语义化智能问数 Agent",
    description="税务-账务对账智能分析系统",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
from app.api.router_v2 import api_router
app.include_router(api_router, prefix="/api/v1")

# WebSocket 路由 — 多智能体协作版
from app.api.chat_v3 import router as chat_router
app.include_router(chat_router)


@app.get("/")
async def root():
    return {"message": "TDA-TDP 语义化智能问数 Agent 系统", "status": "running"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.APP_HOST, port=settings.APP_PORT, reload=True)
