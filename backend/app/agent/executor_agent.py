"""Executor Agent — executes tool calls according to the DAG plan."""

from __future__ import annotations

import json
import time
from typing import Any

from app.agent.prompts.executor_prompt_clean import EXECUTOR_SYSTEM_PROMPT, EXECUTOR_NODE_TEMPLATE
from app.agent.plan_presentation import summarize_tool_action, summarize_observation_metadata
from app.mcp.tools.registry_v2 import TOOL_DEFINITIONS, TOOL_FUNCTIONS


class ExecutionResult:
    """Result of executing a single plan node."""

    __slots__ = ("node_id", "tool_name", "tool_args", "raw_result", "thinking", "duration_ms", "error")

    def __init__(
        self,
        node_id: str,
        tool_name: str = "",
        tool_args: dict[str, Any] | None = None,
        raw_result: Any = None,
        thinking: str = "",
        duration_ms: int = 0,
        error: str = "",
    ):
        self.node_id = node_id
        self.tool_name = tool_name
        self.tool_args = tool_args or {}
        self.raw_result = raw_result
        self.thinking = thinking
        self.duration_ms = duration_ms
        self.error = error


class ExecutorAgent:
    """Executes plan nodes by calling tools via LLM."""

    def __init__(self, llm: Any):
        self.llm = llm

    async def execute_node(
        self,
        node: dict[str, Any],
        previous_results: dict[str, ExecutionResult],
        plan_graph: dict[str, Any],
    ) -> ExecutionResult:
        """Execute a single plan node and return the result."""
        node_id = node.get("id", "")
        node_kind = node.get("kind", "task")

        # For goal-type nodes, no tool call needed
        if node_kind == "goal":
            return ExecutionResult(
                node_id=node_id,
                thinking=f"已明确目标：{node.get('title', '')}",
            )

        # Build context from previous results
        prev_summary = self._build_previous_summary(previous_results)
        user_content = EXECUTOR_NODE_TEMPLATE.format(
            node_title=node.get("title", ""),
            node_detail=node.get("detail", ""),
            tool_hints=", ".join(node.get("tool_hints", [])) or "自动选择",
            done_when=node.get("done_when", ""),
            previous_results=prev_summary or "暂无已有结果。",
        )

        try:
            response = await self.llm.chat(
                messages=[
                    {"role": "system", "content": EXECUTOR_SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                tools=TOOL_DEFINITIONS,
                stream=False,
                temperature=0.0,
            )

            message = response.choices[0].message
            thinking = (message.content or "").strip()

            # No tool call — LLM decided no tool needed
            if not message.tool_calls:
                return ExecutionResult(
                    node_id=node_id,
                    thinking=thinking or f"节点 {node.get('title', '')} 不需要工具调用。",
                )

            # Execute the first tool call
            tool_call = message.tool_calls[0]
            tool_name = tool_call.function.name
            try:
                tool_args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                tool_args = {}

            tool_fn = TOOL_FUNCTIONS.get(tool_name)
            if not tool_fn:
                return ExecutionResult(
                    node_id=node_id,
                    tool_name=tool_name,
                    tool_args=tool_args,
                    error=f"未知工具: {tool_name}",
                    thinking=thinking,
                )

            t0 = time.monotonic()
            raw_result = await tool_fn(**tool_args)
            duration_ms = int((time.monotonic() - t0) * 1000)

            return ExecutionResult(
                node_id=node_id,
                tool_name=tool_name,
                tool_args=tool_args,
                raw_result=raw_result,
                thinking=thinking,
                duration_ms=duration_ms,
            )

        except Exception as exc:
            return ExecutionResult(
                node_id=node_id,
                error=f"执行异常: {exc}",
            )

    def build_action_metadata(
        self,
        exec_result: ExecutionResult,
        plan_graph: dict[str, Any],
    ) -> dict[str, Any]:
        """Build metadata dict for an action event."""
        return summarize_tool_action(
            tool_name=exec_result.tool_name,
            tool_args=exec_result.tool_args,
            plan_graph=plan_graph,
            plan_node_id=exec_result.node_id,
        )

    def build_observation_metadata(
        self,
        exec_result: ExecutionResult,
        plan_graph: dict[str, Any],
    ) -> dict[str, Any]:
        """Build metadata dict for an observation event."""
        return summarize_observation_metadata(
            tool_name=exec_result.tool_name,
            result=exec_result.raw_result,
            duration_ms=exec_result.duration_ms,
            plan_graph=plan_graph,
            plan_node_id=exec_result.node_id,
        )

    def _build_previous_summary(self, previous_results: dict[str, ExecutionResult]) -> str:
        """Summarize previous execution results for context."""
        if not previous_results:
            return ""
        lines = []
        for node_id, result in previous_results.items():
            if result.error:
                lines.append(f"- {node_id}: 失败 - {result.error}")
            elif result.tool_name:
                result_str = ""
                if isinstance(result.raw_result, dict):
                    if result.raw_result.get("row_count") is not None:
                        result_str = f"返回 {result.raw_result['row_count']} 行"
                    elif result.raw_result.get("count") is not None:
                        result_str = f"共 {result.raw_result['count']} 项"
                    elif result.raw_result.get("columns"):
                        result_str = f"共 {len(result.raw_result['columns'])} 个字段"
                lines.append(f"- {node_id}: {result.tool_name} → {result_str or '已完成'}")
            else:
                lines.append(f"- {node_id}: {result.thinking[:60]}")
        return "\n".join(lines)
