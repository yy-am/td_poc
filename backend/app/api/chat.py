"""WebSocket chat endpoint with persisted conversation history."""

from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.agent.react_agent_v4 import ReactAgent
from app.database import AsyncSessionLocal
from app.models.semantic import SysConversation, SysConversationMessage

router = APIRouter()

# session_id -> ReactAgent
_agents: dict[str, ReactAgent] = {}


async def _load_conversation_history(session_id: str) -> list[dict[str, str]]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(SysConversationMessage)
            .where(SysConversationMessage.session_id == session_id)
            .order_by(SysConversationMessage.created_at.desc(), SysConversationMessage.id.desc())
            .limit(40)
        )
        rows = list(reversed(result.scalars().all()))

    history: list[dict[str, str]] = []
    for row in rows:
        if row.role not in {"user", "assistant"}:
            continue
        history.append({"role": row.role, "content": row.content})
    return history


async def _ensure_conversation(session_id: str) -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(SysConversation).where(SysConversation.session_id == session_id))
        conv = result.scalar_one_or_none()
        if conv is None:
            conv = SysConversation(session_id=session_id, user_id="default", title=f"新会话 {session_id}", status="active")
            db.add(conv)
            await db.commit()


def _summarize_steps(steps: list[dict[str, object]]) -> list[dict[str, object]]:
    summary: list[dict[str, object]] = []
    for step in steps:
        metadata = step.get("metadata") or {}
        summary.append(
            {
                "type": step.get("type"),
                "step_number": step.get("step_number"),
                "title": metadata.get("plan_title")
                or metadata.get("tool_label")
                or metadata.get("sql_summary")
                or step.get("content", ""),
                "tool_name": metadata.get("tool_name"),
                "tool_label": metadata.get("tool_label"),
                "tool_summary": metadata.get("tool_summary"),
                "sql_summary": metadata.get("sql_summary"),
                "result_summary": metadata.get("result_summary"),
                "is_final": step.get("is_final", False),
            }
        )
    return summary


async def _persist_turn(session_id: str, user_content: str, final_step: dict[str, object], steps: list[dict[str, object]]) -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(SysConversation).where(SysConversation.session_id == session_id))
        conv = result.scalar_one_or_none()
        if conv is None:
            conv = SysConversation(session_id=session_id, user_id="default", title=f"新会话 {session_id}", status="active")
            db.add(conv)
            await db.flush()

        db.add(
            SysConversationMessage(
                session_id=session_id,
                role="user",
                content=user_content,
                message_type="text",
                metadata_json=None,
            )
        )

        assistant_payload = {
            "steps": steps,
            "step_summary": _summarize_steps(steps),
            "final_step": final_step,
        }
        final_type = str(final_step.get("type") or "answer")
        db.add(
            SysConversationMessage(
                session_id=session_id,
                role="assistant",
                content=str(final_step.get("content") or ""),
                message_type=final_type,
                metadata_json=json.dumps(assistant_payload, ensure_ascii=False, default=str),
            )
        )

        conv.updated_at = datetime.utcnow()
        await db.commit()


@router.websocket("/ws/chat/{session_id}")
async def chat_websocket(websocket: WebSocket, session_id: str):
    """Stream ReAct steps over WebSocket and persist the turn when complete."""
    await websocket.accept()

    if session_id not in _agents:
        agent = ReactAgent(session_id=session_id)
        agent.conversation_history = await _load_conversation_history(session_id)
        _agents[session_id] = agent
    agent = _agents[session_id]

    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                user_content = str(msg.get("content", ""))
            except json.JSONDecodeError:
                user_content = data

            if not user_content.strip():
                continue

            emitted_steps: list[dict[str, object]] = []
            final_step: dict[str, object] | None = None

            async for step in agent.run(user_content):
                payload = step.to_dict()
                emitted_steps.append(payload)
                if step.is_final:
                    final_step = payload
                await websocket.send_json(payload)

            if final_step is not None:
                await _persist_turn(session_id, user_content, final_step, emitted_steps)

    except WebSocketDisconnect:
        if session_id in _agents:
            del _agents[session_id]
    except Exception as exc:
        try:
            await websocket.send_json(
                {
                    "type": "error",
                    "content": f"服务端错误: {exc}",
                    "is_final": True,
                    "step_number": 0,
                    "metadata": {},
                    "timestamp": "",
                }
            )
        except Exception:
            pass
