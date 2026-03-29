"""Health check API."""
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db

router = APIRouter()
settings = get_settings()


@router.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    result = await db.execute(text("SELECT 1"))
    database_ok = result.scalar_one() == 1

    return {
        "status": "ok" if database_ok else "degraded",
        "database": {
            "ok": database_ok,
            "dialect": settings.database_dialect,
        },
    }
