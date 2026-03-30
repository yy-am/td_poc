"""Executor Agent with runtime grounding and stricter tool routing."""

from __future__ import annotations

import json
import time
from typing import Any

from app.agent.plan_presentation import summarize_observation_metadata, summarize_tool_action
from app.agent.prompts.executor_prompt_v3 import (
    EXECUTOR_NODE_TEMPLATE,
    EXECUTOR_REPAIR_TEMPLATE,
    EXECUTOR_SYSTEM_PROMPT,
)
from app.mcp.tools.registry_v2 import TOOL_DEFINITIONS, TOOL_FUNCTIONS

TOOL_DEFINITION_MAP = {
    tool_def["function"]["name"]: tool_def
    for tool_def in TOOL_DEFINITIONS
    if tool_def.get("type") == "function" and tool_def.get("function")
}


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
        user_query: str,
        runtime_context: dict[str, Any] | None = None,
        understanding_result: dict[str, Any] | None = None,
    ) -> ExecutionResult:
        """Execute a single plan node and return the result."""
        node_id = node.get("id", "")
        node_kind = node.get("kind", "task")
        runtime_context = runtime_context or {}

        if node_kind in {"goal", "answer"}:
            return ExecutionResult(
                node_id=node_id,
                thinking=f"当前节点主要是组织结论：{node.get('title', '')}",
            )

        prev_summary = self._build_previous_summary(previous_results)
        user_content = EXECUTOR_NODE_TEMPLATE.format(
            user_query=user_query,
            node_title=node.get("title", ""),
            node_detail=node.get("detail", ""),
            tool_hints=", ".join(node.get("tool_hints", [])) or "自动选择",
            done_when=node.get("done_when", ""),
            semantic_binding=self._format_semantic_binding(node.get("semantic_binding")),
            understanding_result=self._format_understanding_result(understanding_result),
            runtime_context=self._format_runtime_context(runtime_context),
            previous_results=prev_summary or "暂无已有结果。",
        )

        try:
            response = await self.llm.chat(
                messages=[
                    {"role": "system", "content": EXECUTOR_SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                tools=self._select_tool_definitions(node, runtime_context),
                stream=False,
                temperature=0.0,
                max_tokens=700,
            )

            message = response.choices[0].message
            thinking = (message.content or "").strip()

            if not message.tool_calls:
                return ExecutionResult(
                    node_id=node_id,
                    thinking=thinking or f"节点 {node.get('title', '')} 不需要额外工具调用。",
                )

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

            if self._should_attempt_repair(raw_result, tool_name):
                repaired = await self._attempt_tool_repair(
                    node=node,
                    user_query=user_query,
                    runtime_context=runtime_context,
                    understanding_result=understanding_result,
                    tool_name=tool_name,
                    tool_args=tool_args,
                    error_message=str(raw_result.get("error") or ""),
                )
                if repaired is not None:
                    repaired.node_id = node_id
                    if thinking and repaired.thinking:
                        repaired.thinking = f"{thinking}\n\n{repaired.thinking}"
                    elif thinking and not repaired.thinking:
                        repaired.thinking = thinking
                    return repaired

            return ExecutionResult(
                node_id=node_id,
                tool_name=tool_name,
                tool_args=tool_args,
                raw_result=raw_result,
                thinking=thinking,
                duration_ms=duration_ms,
            )
        except Exception as exc:
            return ExecutionResult(node_id=node_id, error=f"执行异常: {exc}")

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

    def _select_tool_definitions(
        self,
        node: dict[str, Any],
        runtime_context: dict[str, Any],
    ) -> list[dict[str, Any]]:
        node_kind = str(node.get("kind") or "task")
        hints = [hint for hint in node.get("tool_hints") or [] if hint in TOOL_DEFINITION_MAP]
        query_mode = runtime_context.get("query_mode")
        semantic_binding = node.get("semantic_binding") if isinstance(node.get("semantic_binding"), dict) else {}
        has_semantic_binding = bool(semantic_binding.get("models"))

        if node_kind == "schema":
            if hints and any(name != "metadata_query" for name in hints):
                allowed_names = hints
            else:
                allowed_names = ["metadata_query"]
        elif node_kind == "knowledge":
            allowed_names = ["knowledge_search"]
        elif node_kind == "visualization":
            allowed_names = ["chart_generator"]
        elif has_semantic_binding:
            allowed_names = ["semantic_query", "sql_executor", "knowledge_search"]
        elif hints:
            allowed_names = hints
        elif node_kind in {"query", "analysis"} and query_mode == "metadata":
            allowed_names = ["metadata_query"]
        elif node_kind in {"query", "analysis"}:
            allowed_names = ["semantic_query", "sql_executor", "knowledge_search"]
        else:
            allowed_names = list(TOOL_DEFINITION_MAP)

        if node_kind in {"query", "analysis"} and query_mode != "metadata" and "metadata_query" in allowed_names and "metadata_query" not in hints:
            allowed_names = [name for name in allowed_names if name != "metadata_query"]

        definitions = [TOOL_DEFINITION_MAP[name] for name in allowed_names if name in TOOL_DEFINITION_MAP]
        return definitions or TOOL_DEFINITIONS

    def _format_runtime_context(self, runtime_context: dict[str, Any]) -> str:
        compact = {
            "query_mode": runtime_context.get("query_mode"),
            "classification_confidence": runtime_context.get("classification_confidence"),
            "matched_keywords": runtime_context.get("matched_keywords"),
            "period_hints": runtime_context.get("period_hints"),
            "enterprise_candidates": runtime_context.get("enterprise_candidates"),
            "relevant_table_schemas": runtime_context.get("relevant_table_schemas"),
            "relevant_models": [
                {
                    "name": item.get("name"),
                    "label": item.get("label"),
                    "source_table": item.get("source_table"),
                    "has_yaml_definition": item.get("has_yaml_definition"),
                    "recommended_tool": item.get("recommended_tool"),
                }
                for item in (runtime_context.get("relevant_models") or [])[:4]
            ],
            "relevant_tables": (runtime_context.get("relevant_tables") or [])[:6],
            "execution_guidance": runtime_context.get("execution_guidance"),
        }
        return json.dumps(compact, ensure_ascii=False, indent=2)

    def _format_understanding_result(self, understanding_result: dict[str, Any] | None) -> str:
        if not understanding_result:
            return "暂无"
        compact = {
            "query_mode": understanding_result.get("query_mode"),
            "intent_summary": understanding_result.get("intent_summary"),
            "business_goal": understanding_result.get("business_goal"),
            "entities": understanding_result.get("entities"),
            "dimensions": understanding_result.get("dimensions"),
            "metrics": understanding_result.get("metrics"),
            "comparisons": understanding_result.get("comparisons"),
            "candidate_models": understanding_result.get("candidate_models"),
            "ambiguities": understanding_result.get("ambiguities"),
            "confidence": understanding_result.get("confidence"),
        }
        return json.dumps(compact, ensure_ascii=False, indent=2)

    def _format_semantic_binding(self, semantic_binding: Any) -> str:
        if not isinstance(semantic_binding, dict) or not semantic_binding:
            return "暂无"
        compact = {
            "models": semantic_binding.get("models", []),
            "metrics": semantic_binding.get("metrics", []),
            "dimensions": semantic_binding.get("dimensions", []),
            "filters": semantic_binding.get("filters", []),
            "grain": semantic_binding.get("grain", ""),
            "fallback_to_sql": semantic_binding.get("fallback_to_sql", True),
        }
        return json.dumps(compact, ensure_ascii=False, indent=2)

    def _should_attempt_repair(self, raw_result: Any, tool_name: str) -> bool:
        return (
            tool_name in {"sql_executor", "semantic_query", "metadata_query"}
            and isinstance(raw_result, dict)
            and bool(raw_result.get("error"))
        )

    async def _attempt_tool_repair(
        self,
        node: dict[str, Any],
        user_query: str,
        runtime_context: dict[str, Any],
        understanding_result: dict[str, Any] | None,
        tool_name: str,
        tool_args: dict[str, Any],
        error_message: str,
    ) -> ExecutionResult | None:
        repair_content = EXECUTOR_REPAIR_TEMPLATE.format(
            user_query=user_query,
            node_title=node.get("title", ""),
            node_detail=node.get("detail", ""),
            done_when=node.get("done_when", ""),
            semantic_binding=self._format_semantic_binding(node.get("semantic_binding")),
            understanding_result=self._format_understanding_result(understanding_result),
            runtime_context=self._format_runtime_context(runtime_context),
            tool_name=tool_name,
            tool_args=json.dumps(tool_args, ensure_ascii=False),
            error_message=error_message,
        )

        try:
            response = await self.llm.chat(
                messages=[
                    {"role": "system", "content": EXECUTOR_SYSTEM_PROMPT},
                    {"role": "user", "content": repair_content},
                ],
                tools=self._select_tool_definitions(node, runtime_context),
                stream=False,
                temperature=0.0,
                max_tokens=500,
            )
            message = response.choices[0].message
            thinking = (message.content or "").strip()

            if not message.tool_calls:
                return ExecutionResult(
                    node_id="",
                    thinking=thinking or f"基于错误 `{error_message}` 自动修正失败。",
                    error=error_message,
                )

            repaired_call = message.tool_calls[0]
            repaired_tool_name = repaired_call.function.name
            try:
                repaired_args = json.loads(repaired_call.function.arguments)
            except json.JSONDecodeError:
                repaired_args = {}

            repaired_fn = TOOL_FUNCTIONS.get(repaired_tool_name)
            if not repaired_fn:
                return ExecutionResult(
                    node_id="",
                    tool_name=repaired_tool_name,
                    tool_args=repaired_args,
                    thinking=thinking,
                    error=f"未知工具: {repaired_tool_name}",
                )

            t0 = time.monotonic()
            repaired_result = await repaired_fn(**repaired_args)
            duration_ms = int((time.monotonic() - t0) * 1000)

            return ExecutionResult(
                node_id="",
                tool_name=repaired_tool_name,
                tool_args=repaired_args,
                raw_result=repaired_result,
                thinking=(thinking + "\n\n已根据报错自动修正并重试。").strip(),
                duration_ms=duration_ms,
                error=str(repaired_result.get("error") or "") if isinstance(repaired_result, dict) else "",
            )
        except Exception as exc:
            return ExecutionResult(
                node_id="",
                thinking=f"根据报错自动修正失败：{exc}",
                error=error_message,
            )

    def _build_previous_summary(self, previous_results: dict[str, ExecutionResult]) -> str:
        """Summarize previous execution results for context."""
        if not previous_results:
            return ""

        lines: list[str] = []
        for node_id, result in previous_results.items():
            if result.error:
                lines.append(f"- {node_id}: 失败 - {result.error}")
                continue

            if result.tool_name:
                result_str = ""
                if isinstance(result.raw_result, dict):
                    if result.raw_result.get("row_count") is not None:
                        result_str = f"返回 {result.raw_result['row_count']} 行"
                    elif result.raw_result.get("count") is not None:
                        result_str = f"共 {result.raw_result['count']} 项"
                    elif result.raw_result.get("columns"):
                        result_str = f"共 {len(result.raw_result['columns'])} 个字段"
                lines.append(f"- {node_id}: {result.tool_name} -> {result_str or '已完成'}")
                continue

            lines.append(f"- {node_id}: {result.thinking[:60]}")

        return "\n".join(lines)
