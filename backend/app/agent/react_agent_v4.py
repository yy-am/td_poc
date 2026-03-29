"""Strict model-planned ReAct agent.

This version only proceeds when a real LLM-generated plan graph is available.
It never renders or executes against a fallback plan as if it were agentic.
"""

from __future__ import annotations

import asyncio
import copy
import json
import re
import time
from datetime import datetime
from typing import Any, AsyncGenerator, Optional

from app.agent.plan_presentation import (
    attach_plan_context,
    build_plan_metadata,
    plan_graph_signature,
    select_plan_node,
    summarize_observation_metadata,
    summarize_tool_action,
)
from app.agent.planner import generate_initial_plan, update_plan_graph
from app.agent.system_prompt_v3 import build_system_prompt
from app.llm.client import get_llm_client
from app.mcp.tools.registry import TOOL_DEFINITIONS, TOOL_FUNCTIONS


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
    """ReAct agent with a strict requirement for a real plan graph."""

    MAX_STEPS = 10
    INITIAL_PLAN_TIMEOUT_SECONDS = 25.0

    def __init__(self, session_id: str = "default"):
        self.session_id = session_id
        self.llm = get_llm_client()
        self.conversation_history: list[dict[str, Any]] = []

    async def run(self, user_query: str) -> AsyncGenerator[AgentStep, None]:
        step_num = 0
        yield AgentStep(
            type="status",
            content="正在生成真实计划图，生成完成后会先展示全景图，再进入实际工具执行。",
            step_number=step_num,
            metadata={"plan_source": "pending"},
        )

        plan_task = asyncio.create_task(
            generate_initial_plan(self.llm, user_query, self.conversation_history)
        )
        try:
            plan_graph = await asyncio.wait_for(
                asyncio.shield(plan_task),
                timeout=self.INITIAL_PLAN_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            yield AgentStep(
                type="error",
                content="真实计划图生成超时。本轮已停止执行，避免展示伪 agentic 过程。请重试，或缩小问题范围后再试。",
                step_number=step_num,
                metadata={"plan_source": "timeout"},
                is_final=True,
            )
            return

        if plan_graph.get("source") != "llm":
            yield AgentStep(
                type="error",
                content="本轮没有拿到可验证的模型计划图，因此不会继续执行工具，避免把兜底逻辑伪装成 agentic 过程。",
                step_number=step_num,
                metadata={"plan_source": plan_graph.get("source", "fallback")},
                is_final=True,
            )
            return

        last_plan_signature = plan_graph_signature(plan_graph)
        yield AgentStep(
            type="plan",
            content="先展示模型生成的执行全景图，再按真实工具链路逐步推进；如路径变化，会同步更新计划图。",
            step_number=step_num,
            metadata=build_plan_metadata(plan_graph, title=plan_graph.get("title")),
        )

        current_node = select_plan_node(plan_graph)
        if current_node:
            yield AgentStep(
                type="status",
                content=f"当前先推进“{current_node['title']}”。",
                step_number=step_num,
                metadata=attach_plan_context(plan_graph, current_node.get("id")),
            )

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": build_system_prompt()},
            *self.conversation_history,
            {"role": "user", "content": user_query},
        ]

        for step in range(self.MAX_STEPS):
            step_num = step + 1
            start_time = time.time()
            current_node = select_plan_node(plan_graph)
            guided_messages = self._build_guided_messages(messages, plan_graph, current_node)

            try:
                response = await self.llm.chat(
                    messages=guided_messages,
                    tools=TOOL_DEFINITIONS,
                    stream=False,
                )
            except Exception as exc:
                yield AgentStep(
                    type="error",
                    content=f"LLM 调用失败: {exc}",
                    step_number=step_num,
                    metadata=attach_plan_context(plan_graph),
                    is_final=True,
                )
                return

            choice = response.choices[0]
            message = choice.message
            duration_ms = int((time.time() - start_time) * 1000)
            cleaned_content = sanitize_user_visible_text(message.content or "")

            assistant_message: dict[str, Any] = {
                "role": "assistant",
                "content": cleaned_content,
            }
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

            current_node_id = current_node.get("id") if current_node else None
            if cleaned_content and message.tool_calls:
                thinking_metadata = attach_plan_context(plan_graph, current_node_id)
                thinking_metadata["duration_ms"] = duration_ms
                yield AgentStep(
                    type="thinking",
                    content=cleaned_content,
                    step_number=step_num,
                    metadata=thinking_metadata,
                )

            if not message.tool_calls:
                final_content = cleaned_content or "分析完成。"
                updated_plan = await self._update_plan_after_event(
                    plan_graph=plan_graph,
                    last_signature=last_plan_signature,
                    step_number=step_num,
                    user_query=user_query,
                    execution_event={
                        "phase": "final_answer",
                        "assistant_thinking": cleaned_content[:2000],
                        "final_answer": final_content[:4000],
                    },
                )
                if updated_plan["plan_step"] is not None:
                    yield updated_plan["plan_step"]
                plan_graph = updated_plan["plan_graph"]
                last_plan_signature = updated_plan["last_signature"]

                answer_node = select_plan_node(plan_graph) or current_node
                answer_metadata = attach_plan_context(
                    plan_graph,
                    answer_node.get("id") if answer_node else None,
                )
                yield AgentStep(
                    type="answer",
                    content=final_content,
                    step_number=step_num,
                    metadata=answer_metadata,
                    is_final=True,
                )
                self.conversation_history.append({"role": "user", "content": user_query})
                self.conversation_history.append({"role": "assistant", "content": final_content})
                return

            for tool_call in message.tool_calls:
                current_node = select_plan_node(plan_graph)
                current_node_id = current_node.get("id") if current_node else None

                tool_name = tool_call.function.name
                try:
                    tool_args = json.loads(tool_call.function.arguments) if tool_call.function.arguments else {}
                except json.JSONDecodeError:
                    tool_args = {}

                action_metadata = summarize_tool_action(
                    tool_name,
                    tool_args,
                    plan_graph=plan_graph,
                    plan_node_id=current_node_id,
                )
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
                    plan_graph=plan_graph,
                    plan_node_id=current_node_id,
                )
                display_content = result_str if len(result_str) < 2000 else result_str[:2000] + "...（结果已截断）"

                yield AgentStep(
                    type="observation",
                    content=display_content,
                    step_number=step_num,
                    metadata=observation_metadata,
                )

                updated_plan = await self._update_plan_after_event(
                    plan_graph=plan_graph,
                    last_signature=last_plan_signature,
                    step_number=step_num,
                    user_query=user_query,
                    execution_event={
                        "phase": "tool_result",
                        "assistant_thinking": cleaned_content[:2000],
                        "plan_node_id": current_node_id,
                        "plan_node_title": current_node.get("title") if current_node else "",
                        "tool_name": tool_name,
                        "tool_args": trim_for_planner(tool_args),
                        "tool_result_summary": observation_metadata.get("result_summary"),
                        "tool_result": trim_for_planner(result),
                    },
                )
                if updated_plan["plan_step"] is not None:
                    yield updated_plan["plan_step"]
                plan_graph = updated_plan["plan_graph"]
                last_plan_signature = updated_plan["last_signature"]

                messages.append(
                    {
                        "role": "tool",
                        "content": result_str[:8000],
                        "tool_call_id": tool_call.id,
                    }
                )

        plan_graph = complete_plan_graph(plan_graph, reason="已达到最大推理步数。")
        yield AgentStep(
            type="plan_update",
            content="执行步数达到上限，计划图已收束。",
            step_number=step_num + 1,
            metadata=build_plan_metadata(
                plan_graph,
                title=plan_graph.get("title"),
                change_reason="已达到最大推理步数。",
            ),
        )
        yield AgentStep(
            type="answer",
            content="已达到最大推理步数，请把问题描述得更具体一些，或缩小分析范围。",
            step_number=step_num + 1,
            metadata=attach_plan_context(plan_graph),
            is_final=True,
        )

    async def _update_plan_after_event(
        self,
        plan_graph: dict[str, Any],
        last_signature: tuple[Any, ...],
        step_number: int,
        user_query: str,
        execution_event: dict[str, Any],
    ) -> dict[str, Any]:
        candidate = await update_plan_graph(
            self.llm,
            user_query=user_query,
            current_plan=plan_graph,
            recent_execution=execution_event,
        )

        if candidate.get("source") == "fallback" and plan_graph.get("source") == "llm":
            candidate = plan_graph

        if execution_event.get("phase") == "final_answer" and plan_graph_signature(candidate) == last_signature:
            candidate = complete_plan_graph(plan_graph, reason="已生成最终回答。")

        current_signature = plan_graph_signature(candidate)
        if current_signature == last_signature:
            return {
                "plan_graph": candidate,
                "last_signature": last_signature,
                "plan_step": None,
            }

        return {
            "plan_graph": candidate,
            "last_signature": current_signature,
            "plan_step": AgentStep(
                type="plan_update",
                content="已根据最新证据修订执行计划图。",
                step_number=step_number,
                metadata=build_plan_metadata(
                    candidate,
                    title=candidate.get("title"),
                    change_reason=candidate.get("change_reason") or execution_event.get("tool_result_summary") or "",
                ),
            ),
        }

    def _build_guided_messages(
        self,
        messages: list[dict[str, Any]],
        plan_graph: dict[str, Any],
        current_node: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        guidance = self._build_runtime_guidance(plan_graph, current_node)
        if not messages:
            return [{"role": "system", "content": guidance}]
        first = messages[0]
        if first.get("role") != "system":
            return [{"role": "system", "content": guidance}, *messages]
        return [first, {"role": "system", "content": guidance}, *messages[1:]]

    @staticmethod
    def _build_runtime_guidance(
        plan_graph: dict[str, Any],
        current_node: dict[str, Any] | None,
    ) -> str:
        node_title = current_node.get("title") if current_node else "当前步骤"
        node_kind = current_node.get("kind") if current_node else "task"
        tool_hints = ", ".join(current_node.get("tool_hints") or []) or "none"
        lines = [
            "内部执行约束：以下内容绝不能直接输出给用户。",
            f"active_node={node_title}",
            f"node_kind={node_kind}",
            f"tool_hints={tool_hints}",
            "直接推进当前节点，不要输出欢迎语、能力介绍或泛化建议。",
            "能由一次工具调用直接回答时，立刻调用工具，不要反问。",
            "metadata/schema 问题优先 metadata_query。",
            "指标、聚合、分组问题优先 semantic_query；语义层无法表达时再用 sql_executor。",
            "最终回答只保留结论、关键数字和依据，不要输出计划上下文、节点名或内部提示。",
        ]
        return "\n".join(lines)


def sanitize_user_visible_text(text: str) -> str:
    """Remove internal runtime guidance that the model may accidentally echo."""
    if not text:
        return ""

    cleaned_lines: list[str] = []
    for line in text.replace("\r\n", "\n").split("\n"):
        stripped = line.strip()
        if not stripped:
            cleaned_lines.append("")
            continue
        if re.match(r"^\*{0,2}plan context[:：]", stripped, flags=re.IGNORECASE):
            continue
        if re.match(r"^(current|internal) (plan|node|tool)", stripped, flags=re.IGNORECASE):
            continue
        if stripped.startswith("active_node=") or stripped.startswith("node_kind=") or stripped.startswith("tool_hints="):
            continue
        if stripped.startswith("当前计划") or stripped.startswith("内部计划") or stripped.startswith("内部执行约束"):
            continue
        cleaned_lines.append(line)

    cleaned = "\n".join(cleaned_lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned


def complete_plan_graph(plan_graph: dict[str, Any], reason: str) -> dict[str, Any]:
    updated = copy.deepcopy(plan_graph)
    answer_node_id: str | None = None
    for node in updated.get("nodes", []):
        if node.get("kind") == "answer":
            answer_node_id = node.get("id")
            break

    for node in updated.get("nodes", []):
        if node.get("status") == "in_progress":
            node["status"] = "completed"

    if answer_node_id:
        for node in updated.get("nodes", []):
            if node.get("id") == answer_node_id:
                node["status"] = "completed"
        updated["active_node_ids"] = [answer_node_id]
    else:
        updated["active_node_ids"] = []

    updated["change_reason"] = reason
    return updated


def trim_for_planner(value: Any, max_items: int = 8, max_text: int = 600) -> Any:
    if isinstance(value, dict):
        trimmed: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= max_items:
                trimmed["__truncated__"] = True
                break
            trimmed[str(key)] = trim_for_planner(item, max_items=max_items, max_text=max_text)
        return trimmed

    if isinstance(value, list):
        items = [trim_for_planner(item, max_items=max_items, max_text=max_text) for item in value[:max_items]]
        if len(value) > max_items:
            items.append({"__truncated__": True})
        return items

    if isinstance(value, str):
        return value[:max_text]

    return value
