"""Conversation/session management API."""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.semantic import SysConversation, SysConversationMessage
from app.schemas.chat import (
    ConversationMessageResponse,
    SessionCreate,
    SessionResponse,
    SessionUpdate,
)

router = APIRouter()


@router.get("")
async def list_sessions(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(SysConversation).order_by(SysConversation.updated_at.desc(), SysConversation.created_at.desc())
    )
    sessions = result.scalars().all()
    return [SessionResponse.model_validate(session) for session in sessions]


@router.post("")
async def create_session(body: SessionCreate, db: AsyncSession = Depends(get_db)):
    session_id = str(uuid.uuid4())[:8]
    conv = SysConversation(
        session_id=session_id,
        user_id=body.user_id,
        title=body.title or f"新会话 {session_id}",
        status="active",
    )
    db.add(conv)
    await db.commit()
    await db.refresh(conv)
    return SessionResponse.model_validate(conv)


@router.get("/{session_id}/messages")
async def get_messages(session_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(SysConversationMessage)
        .where(SysConversationMessage.session_id == session_id)
        .order_by(SysConversationMessage.created_at, SysConversationMessage.id)
    )
    messages = result.scalars().all()
    payload: list[ConversationMessageResponse] = []
    for message in messages:
        metadata = None
        if message.metadata_json:
            try:
                metadata = json.loads(message.metadata_json)
            except json.JSONDecodeError:
                metadata = {"raw": message.metadata_json}
        payload.append(
            ConversationMessageResponse(
                id=message.id,
                session_id=message.session_id,
                role=message.role,
                content=message.content,
                message_type=message.message_type,
                metadata=metadata,
                created_at=message.created_at,
            )
        )
    return payload


@router.patch("/{session_id}")
async def update_session(session_id: str, body: SessionUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SysConversation).where(SysConversation.session_id == session_id))
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")

    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(conv, key, value)
    await db.commit()
    await db.refresh(conv)
    return SessionResponse.model_validate(conv)


@router.delete("/{session_id}")
async def delete_session(session_id: str, db: AsyncSession = Depends(get_db)):
    await db.execute(delete(SysConversationMessage).where(SysConversationMessage.session_id == session_id))
    await db.execute(delete(SysConversation).where(SysConversation.session_id == session_id))
    await db.commit()
    return {"status": "deleted"}
