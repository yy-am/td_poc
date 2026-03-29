"""WebSocket chat endpoint backed by the model-planned ReAct agent."""

from __future__ import annotations

import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.agent.react_agent_v3 import ReactAgent

router = APIRouter()

_agents: dict[str, ReactAgent] = {}


@router.websocket("/ws/chat/{session_id}")
async def chat_websocket(websocket: WebSocket, session_id: str):
    await websocket.accept()

    if session_id not in _agents:
        _agents[session_id] = ReactAgent(session_id=session_id)
    agent = _agents[session_id]

    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                user_content = msg.get("content", "")
            except json.JSONDecodeError:
                user_content = data

            if not user_content.strip():
                continue

            async for step in agent.run(user_content):
                await websocket.send_json(step.to_dict())
    except WebSocketDisconnect:
        _agents.pop(session_id, None)
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
