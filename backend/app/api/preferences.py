"""用户偏好 API"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.semantic import SysUserPreference
from app.schemas.chat import PreferenceUpdate

router = APIRouter()


@router.get("/{user_id}")
async def get_preferences(user_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(SysUserPreference).where(SysUserPreference.user_id == user_id)
    )
    prefs = result.scalars().all()
    return {p.preference_key: p.preference_value for p in prefs}


@router.put("/{user_id}")
async def update_preference(user_id: str, body: PreferenceUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(SysUserPreference).where(
            SysUserPreference.user_id == user_id,
            SysUserPreference.preference_key == body.preference_key,
        )
    )
    pref = result.scalar_one_or_none()
    if pref:
        pref.preference_value = body.preference_value
        pref.usage_count += 1
    else:
        pref = SysUserPreference(
            user_id=user_id,
            preference_type=body.preference_type,
            preference_key=body.preference_key,
            preference_value=body.preference_value,
        )
        db.add(pref)
    await db.commit()
    return {"status": "updated"}
