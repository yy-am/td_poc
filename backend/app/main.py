"""FastAPI application entrypoint."""

from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Ensure project root is importable when running as module/script.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import get_settings
from app.database import close_database, init_database

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_database()
    yield
    await close_database()


app = FastAPI(
    title="TDA-TDP Semantic Query Agent",
    description="Tax and accounting reconciliation analysis service",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.api.router_v2 import api_router
from app.api.chat_v3 import router as chat_router

app.include_router(api_router, prefix="/api/v1")
app.include_router(chat_router)


@app.get("/")
async def root():
    return {"message": "TDA-TDP Semantic Query Agent", "status": "running"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.APP_HOST, port=settings.APP_PORT, reload=True)