"""WebSocket chat endpoint v3 — multi-agent orchestration."""

from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.agent.orchestrator import MultiAgentOrchestrator
from app.database import AsyncSessionLocal
from app.llm.client import get_llm_client
from app.models.semantic import SysConversation, SysConversationMessage

router = APIRouter()

_orchestrators: dict[str, MultiAgentOrchestrator] = {}


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


def _summarize_events(events: list[dict[str, object]]) -> list[dict[str, object]]:
    summary: list[dict[str, object]] = []
    for event in events:
        metadata = event.get("metadata") or {}
        summary.append({
            "type": event.get("type"),
            "agent": event.get("agent"),
            "step_number": event.get("step_number"),
            "content": str(event.get("content", ""))[:200],
            "is_final": event.get("is_final", False),
            "tool_name": metadata.get("tool_name"),
            "verdict": metadata.get("verdict"),
            "node_id": metadata.get("node_id"),
        })
    return summary


async def _persist_turn(
    session_id: str,
    user_content: str,
    final_event: dict[str, object],
    events: list[dict[str, object]],
) -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(SysConversation).where(SysConversation.session_id == session_id)
        )
        conv = result.scalar_one_or_none()
        if conv is None:
            conv = SysConversation(
                session_id=session_id,
                user_id="default",
                title=f"新会话 {session_id}",
                status="active",
            )
            db.add(conv)
            await db.flush()

        db.add(SysConversationMessage(
            session_id=session_id,
            role="user",
            content=user_content,
            message_type="text",
            metadata_json=None,
        ))

        assistant_payload = {
            "steps": events,
            "step_summary": _summarize_events(events),
            "final_step": final_event,
        }
        db.add(SysConversationMessage(
            session_id=session_id,
            role="assistant",
            content=str(final_event.get("content") or ""),
            message_type=str(final_event.get("type") or "answer"),
            metadata_json=json.dumps(assistant_payload, ensure_ascii=False, default=str),
        ))

        conv.updated_at = datetime.utcnow()
        await db.commit()


@router.websocket("/ws/chat/{session_id}")
async def chat_websocket_v3(websocket: WebSocket, session_id: str):
    """Multi-agent orchestrated chat over WebSocket."""
    await websocket.accept()

    if session_id not in _orchestrators:
        llm = get_llm_client()
        orchestrator = MultiAgentOrchestrator(llm)
        orchestrator.conversation_history = await _load_conversation_history(session_id)
        _orchestrators[session_id] = orchestrator
    orchestrator = _orchestrators[session_id]

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

            emitted_events: list[dict[str, object]] = []
            final_event: dict[str, object] | None = None

            async for event in orchestrator.run(user_content):
                payload = event.to_dict()
                emitted_events.append(payload)
                if event.is_final:
                    final_event = payload
                await websocket.send_json(payload)

            if final_event is not None:
                await _persist_turn(session_id, user_content, final_event, emitted_events)

    except WebSocketDisconnect:
        _orchestrators.pop(session_id, None)
    except Exception as exc:
        try:
            await websocket.send_json({
                "type": "error",
                "agent": "orchestrator",
                "content": f"服务端错误: {exc}",
                "is_final": True,
                "step_number": 0,
                "metadata": {},
                "timestamp": datetime.now().isoformat(),
            })
        except Exception:
            pass
