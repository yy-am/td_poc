"""ReAct agent with user-friendly plan and execution updates."""

from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Any, AsyncGenerator, Optional

from app.agent.presentation import (
    build_initial_plan,
    build_plan_metadata,
    mark_plan_for_final_answer,
    mark_plan_for_tool_result,
    mark_plan_for_tool_start,
    summarize_observation_metadata,
    summarize_tool_action,
)
from app.agent.system_prompt_v3 import build_system_prompt
from app.llm.client import get_llm_client
from app.mcp.tools.registry_v2 import TOOL_DEFINITIONS, TOOL_FUNCTIONS


class AgentStep:
    """Single user-visible step in the agent execution flow."""

    def __init__(
        self,
        type: str,
        content: str,
        step_number: int = 0,
        metadata: Optional[dict[str, Any]] = None,
        is_final: bool = False,
    ):
        self.type = type
        self.content = content
        self.step_number = step_number
        self.metadata = metadata or {}
        self.is_final = is_final
        self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "step_number": self.step_number,
            "content": self.content,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
            "is_final": self.is_final,
        }


class ReactAgent:
    """ReAct agent for the chat experience."""

    MAX_STEPS = 10

    def __init__(self, session_id: str = "default"):
        self.session_id = session_id
        self.llm = get_llm_client()
        self.conversation_history: list[dict[str, Any]] = []

    async def run(self, user_query: str) -> AsyncGenerator[AgentStep, None]:
        """Run the ReAct loop and stream structured steps to the frontend."""
        step_num = 0
        plan_items = build_initial_plan(user_query)
        last_plan_signature = self._plan_signature(plan_items)

        yield AgentStep(
            type="plan",
            content="我会先给您一个执行全景图，再逐步取数、分析，并在路径变化时同步更新计划。",
            step_number=step_num,
            metadata=build_plan_metadata(plan_items, title="本轮执行计划"),
        )
        yield AgentStep(
            type="status",
            content="已生成执行计划，正在确认最合适的分析路径...",
            step_number=step_num,
        )

        system_prompt = build_system_prompt()
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            *self.conversation_history,
            {"role": "user", "content": user_query},
        ]

        for step in range(self.MAX_STEPS):
            step_num = step + 1
            start_time = time.time()

            try:
                response = await self.llm.chat(
                    messages=messages,
                    tools=TOOL_DEFINITIONS,
                    stream=False,
                )
            except Exception as exc:
                yield AgentStep(
                    type="error",
                    content=f"LLM 调用失败: {exc}",
                    step_number=step_num,
                    is_final=True,
                )
                return

            choice = response.choices[0]
            message = choice.message
            duration_ms = int((time.time() - start_time) * 1000)

            assistant_message: dict[str, Any] = {"role": "assistant", "content": message.content or ""}
            if message.tool_calls:
                assistant_message["tool_calls"] = [
                    {
                        "id": tool_call.id,
                        "type": "function",
                        "function": {
                            "name": tool_call.function.name,
                            "arguments": tool_call.function.arguments,
                        },
                    }
                    for tool_call in message.tool_calls
                ]
            messages.append(assistant_message)

            if message.content:
                yield AgentStep(
                    type="thinking",
                    content=message.content.strip(),
                    step_number=step_num,
                    metadata={"duration_ms": duration_ms},
                )

            if not message.tool_calls:
                plan_items, change_reason = mark_plan_for_final_answer(plan_items)
                plan_step, last_plan_signature = self._build_plan_update_if_needed(
                    plan_items=plan_items,
                    last_signature=last_plan_signature,
                    step_number=step_num,
                    change_reason=change_reason,
                )
                if plan_step:
                    yield plan_step

                final_content = message.content or "分析完成。"
                yield AgentStep(
                    type="answer",
                    content=final_content,
                    step_number=step_num,
                    is_final=True,
                )
                self.conversation_history.append({"role": "user", "content": user_query})
                self.conversation_history.append({"role": "assistant", "content": final_content})
                return

            for tool_call in message.tool_calls:
                tool_name = tool_call.function.name
                try:
                    tool_args = json.loads(tool_call.function.arguments) if tool_call.function.arguments else {}
                except json.JSONDecodeError:
                    tool_args = {}

                plan_items, change_reason = mark_plan_for_tool_start(plan_items, tool_name, tool_args)
                plan_step, last_plan_signature = self._build_plan_update_if_needed(
                    plan_items=plan_items,
                    last_signature=last_plan_signature,
                    step_number=step_num,
                    change_reason=change_reason,
                )
                if plan_step:
                    yield plan_step

                action_metadata = summarize_tool_action(tool_name, tool_args, plan_items=plan_items)
                yield AgentStep(
                    type="action",
                    content=action_metadata.get("tool_input_summary") or f"调用工具: {tool_name}",
                    step_number=step_num,
                    metadata=action_metadata,
                )

                tool_fn = TOOL_FUNCTIONS.get(tool_name)
                if tool_fn:
                    try:
                        tool_start = time.time()
                        result = await tool_fn(**tool_args)
                        tool_duration = int((time.time() - tool_start) * 1000)
                    except Exception as exc:
                        result = {"error": f"工具执行出错: {exc}"}
                        tool_duration = 0
                else:
                    result = {"error": f"未知工具: {tool_name}"}
                    tool_duration = 0

                result_str = json.dumps(result, ensure_ascii=False, default=str)
                observation_metadata = summarize_observation_metadata(
                    tool_name,
                    result,
                    tool_duration,
                    plan_items=plan_items,
                )
                display_content = result_str if len(result_str) < 2000 else result_str[:2000] + "...（结果已截断）"

                yield AgentStep(
                    type="observation",
                    content=display_content,
                    step_number=step_num,
                    metadata=observation_metadata,
                )

                plan_items, change_reason = mark_plan_for_tool_result(plan_items, tool_name, result)
                plan_step, last_plan_signature = self._build_plan_update_if_needed(
                    plan_items=plan_items,
                    last_signature=last_plan_signature,
                    step_number=step_num,
                    change_reason=change_reason,
                )
                if plan_step:
                    yield plan_step

                messages.append(
                    {
                        "role": "tool",
                        "content": result_str[:8000],
                        "tool_call_id": tool_call.id,
                    }
                )

        plan_items, change_reason = mark_plan_for_final_answer(plan_items)
        plan_step, _ = self._build_plan_update_if_needed(
            plan_items=plan_items,
            last_signature=last_plan_signature,
            step_number=step_num + 1,
            change_reason=change_reason,
        )
        if plan_step:
            yield plan_step

        yield AgentStep(
            type="answer",
            content="已达到最大推理步数，请尝试把问题描述得更具体一些。",
            step_number=step_num + 1,
            is_final=True,
        )

    @staticmethod
    def _plan_signature(plan_items: list[dict[str, str]]) -> tuple[tuple[str, str], ...]:
        return tuple((item["key"], item["status"]) for item in plan_items)

    def _build_plan_update_if_needed(
        self,
        plan_items: list[dict[str, str]],
        last_signature: tuple[tuple[str, str], ...],
        step_number: int,
        change_reason: str,
    ) -> tuple[AgentStep | None, tuple[tuple[str, str], ...]]:
        current_signature = self._plan_signature(plan_items)
        if current_signature == last_signature:
            return None, last_signature

        return (
            AgentStep(
                type="plan_update",
                content="已根据当前证据更新执行计划。",
                step_number=step_number,
                metadata=build_plan_metadata(
                    plan_items,
                    title="执行计划已更新",
                    change_reason=change_reason,
                ),
            ),
            current_signature,
        )
