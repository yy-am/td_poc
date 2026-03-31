"""Executor Agent with semantic-first tool routing."""

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
    """Executes plan nodes by calling tools via semantic-first routing."""

    def __init__(self, llm: Any):
        self.llm = llm

    @staticmethod
    def _merge_unique(*groups: list[Any]) -> list[str]:
        merged: list[str] = []
        for group in groups:
            for item in group or []:
                text = str(item or "").strip()
                if text and text not in merged:
                    merged.append(text)
        return merged

    async def execute_node(
        self,
        node: dict[str, Any],
        previous_results: dict[str, ExecutionResult],
        plan_graph: dict[str, Any],
        user_query: str,
        runtime_context: dict[str, Any] | None = None,
        understanding_result: dict[str, Any] | None = None,
    ) -> ExecutionResult:
        node_id = node.get("id", "")
        node_kind = node.get("kind", "task")
        runtime_context = runtime_context or {}

        if node_kind in {"goal", "answer"}:
            return ExecutionResult(
                node_id=node_id,
                thinking=f"Current node is organizational only: {node.get('title', '')}",
            )

        direct_result = await self._execute_semantic_first(
            node=node,
            runtime_context=runtime_context,
        )
        if direct_result and not direct_result.error:
            direct_result.node_id = node_id
            return direct_result

        if direct_result and direct_result.error and direct_result.tool_name == "mql_query":
            direct_result.node_id = node_id
            return direct_result

        if direct_result and direct_result.error and self._binding_allows_fallback(node.get("semantic_binding")):
            repaired = await self._attempt_tool_repair(
                node=node,
                user_query=user_query,
                runtime_context=runtime_context,
                understanding_result=understanding_result,
                tool_name=direct_result.tool_name or "semantic_query",
                tool_args=direct_result.tool_args,
                error_message=direct_result.error,
            )
            if repaired is not None and not repaired.error:
                repaired.node_id = node_id
                if direct_result.thinking and repaired.thinking:
                    repaired.thinking = f"{direct_result.thinking}\n\n{repaired.thinking}"
                elif direct_result.thinking and not repaired.thinking:
                    repaired.thinking = direct_result.thinking
                return repaired

        prev_summary = self._build_previous_summary(previous_results)
        user_content = EXECUTOR_NODE_TEMPLATE.format(
            user_query=user_query,
            node_title=node.get("title", ""),
            node_detail=node.get("detail", ""),
            tool_hints=", ".join(node.get("tool_hints", [])) or "auto",
            done_when=node.get("done_when", ""),
            semantic_binding=self._format_semantic_binding(node.get("semantic_binding")),
            understanding_result=self._format_understanding_result(understanding_result),
            runtime_context=self._format_runtime_context(runtime_context),
            previous_results=prev_summary or "none",
        )

        try:
            response = await self.llm.chat(
                messages=[
                    {"role": "system", "content": EXECUTOR_SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                trace={
                    "agent": "executor",
                    "operation": "tool_select",
                    "node_id": node_id,
                    "node_title": node.get("title", ""),
                },
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
                    thinking=thinking or f"No external tool needed for node {node.get('title', '')}",
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
                    error=f"Unknown tool: {tool_name}",
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
                error=str(raw_result.get("error") or "") if isinstance(raw_result, dict) else "",
            )
        except Exception as exc:
            return ExecutionResult(node_id=node_id, error=f"Execution error: {exc}")

    def build_action_metadata(
        self,
        exec_result: ExecutionResult,
        plan_graph: dict[str, Any],
    ) -> dict[str, Any]:
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
        return summarize_observation_metadata(
            tool_name=exec_result.tool_name,
            result=exec_result.raw_result,
            duration_ms=exec_result.duration_ms,
            plan_graph=plan_graph,
            plan_node_id=exec_result.node_id,
        )

    async def _execute_semantic_first(
        self,
        *,
        node: dict[str, Any],
        runtime_context: dict[str, Any],
    ) -> ExecutionResult | None:
        if not self._should_run_semantic_first(node, runtime_context):
            return None

        binding = node.get("semantic_binding") or {}
        use_mql = self._should_use_mql_query(node, runtime_context)
        tool_name = "mql_query" if use_mql else "semantic_query"
        primary_args = (
            self._build_mql_tool_args(binding, runtime_context)
            if use_mql
            else self._build_semantic_tool_args(binding, runtime_context)
        )
        primary_model = primary_args.get("model_name")
        if not primary_model:
            return None

        semantic_tool = TOOL_FUNCTIONS.get(tool_name)
        if semantic_tool is None:
            return None

        try:
            t0 = time.monotonic()
            primary_result = await semantic_tool(**primary_args)
            duration_ms = int((time.monotonic() - t0) * 1000)
        except Exception as exc:
            return ExecutionResult(
                node_id="",
                tool_name=tool_name,
                tool_args=primary_args,
                thinking=f"Semantic-first execution failed on entry model {primary_model}.",
                error=f"{type(exc).__name__}: {exc}",
            )

        if not self._should_attempt_repair(primary_result, tool_name):
            return ExecutionResult(
                node_id="",
                tool_name=tool_name,
                tool_args=primary_args,
                raw_result=primary_result,
                thinking=f"Semantic-first execution used entry model {primary_model} via {tool_name}.",
                duration_ms=duration_ms,
                error=str(primary_result.get("error") or "") if isinstance(primary_result, dict) else "",
            )

        if use_mql:
            return ExecutionResult(
                node_id="",
                tool_name=tool_name,
                tool_args=primary_args,
                raw_result=primary_result,
                thinking=f"TDA-MQL execution failed on entry model {primary_model}.",
                duration_ms=duration_ms,
                error=str(primary_result.get("error") or "") if isinstance(primary_result, dict) else "mql_query failed",
            )

        if str(binding.get("fallback_policy") or "") == "atomic_then_sql":
            atomic_model = self._pick_atomic_fallback_model(binding, runtime_context, exclude=primary_model)
            if atomic_model:
                fallback_args = dict(primary_args)
                fallback_args["model_name"] = atomic_model
                try:
                    t1 = time.monotonic()
                    fallback_result = await semantic_tool(**fallback_args)
                    fallback_duration_ms = int((time.monotonic() - t1) * 1000)
                except Exception as exc:
                    return ExecutionResult(
                        node_id="",
                        tool_name=tool_name,
                        tool_args=fallback_args,
                        thinking=(
                            f"Entry model {primary_model} failed, "
                            f"and semantic fallback model {atomic_model} also failed."
                        ),
                        error=f"{type(exc).__name__}: {exc}",
                    )
                if not self._should_attempt_repair(fallback_result, "semantic_query"):
                    return ExecutionResult(
                        node_id="",
                        tool_name=tool_name,
                        tool_args=fallback_args,
                        raw_result=fallback_result,
                        thinking=(
                            f"Entry model {primary_model} failed, "
                            f"then semantic fallback model {atomic_model} succeeded."
                        ),
                        duration_ms=fallback_duration_ms,
                        error=str(fallback_result.get("error") or "") if isinstance(fallback_result, dict) else "",
                    )

        return ExecutionResult(
            node_id="",
            tool_name=tool_name,
            tool_args=primary_args,
            raw_result=primary_result,
            thinking=f"Semantic-first execution failed on entry model {primary_model}.",
            duration_ms=duration_ms,
            error=str(primary_result.get("error") or "") if isinstance(primary_result, dict) else f"{tool_name} failed",
        )

    def _should_run_semantic_first(self, node: dict[str, Any], runtime_context: dict[str, Any]) -> bool:
        node_kind = str(node.get("kind") or "")
        if node_kind not in {"query", "analysis"}:
            return False
        if runtime_context.get("query_mode") == "metadata":
            return False
        binding = node.get("semantic_binding") if isinstance(node.get("semantic_binding"), dict) else {}
        return bool(binding.get("entry_model"))

    def _should_use_mql_query(self, node: dict[str, Any], runtime_context: dict[str, Any]) -> bool:
        if runtime_context.get("query_mode") == "metadata":
            return False
        binding = node.get("semantic_binding") if isinstance(node.get("semantic_binding"), dict) else {}
        query_language = str(binding.get("query_language") or "").strip().lower()
        hints = {str(item).strip() for item in (node.get("tool_hints") or []) if str(item or "").strip()}
        return query_language == "tda_mql" or "mql_query" in hints

    def _binding_allows_fallback(self, semantic_binding: Any) -> bool:
        if not isinstance(semantic_binding, dict):
            return True
        if str(semantic_binding.get("query_language") or "").strip().lower() == "tda_mql":
            return False
        policy = str(semantic_binding.get("fallback_policy") or "").strip().lower()
        return policy not in {"", "none", "semantic_only"}

    def _pick_atomic_fallback_model(
        self,
        semantic_binding: dict[str, Any],
        runtime_context: dict[str, Any],
        *,
        exclude: str,
    ) -> str:
        model_kinds = {
            str(item.get("name") or ""): str(item.get("semantic_kind") or "")
            for item in (runtime_context.get("relevant_models") or [])
            if item.get("name")
        }
        for name in semantic_binding.get("supporting_models", []) or []:
            if not name or name == exclude:
                continue
            if model_kinds.get(name) == "atomic_fact":
                return str(name)
        return ""

    def _lookup_model_metadata(self, model_name: str, runtime_context: dict[str, Any]) -> dict[str, Any]:
        if not model_name:
            return {}

        for item in runtime_context.get("relevant_models") or []:
            if str(item.get("name") or "").strip() == model_name:
                return item

        for items in (runtime_context.get("semantic_catalog_by_kind") or {}).values():
            for item in items or []:
                if str(item.get("name") or "").strip() == model_name:
                    return item
        return {}

    def _sanitize_requested_fields(
        self,
        requested: list[Any],
        allowed: list[Any],
        *,
        fallback_count: int,
    ) -> list[str]:
        requested_names = self._merge_unique(requested or [])
        allowed_names = self._merge_unique(allowed or [])
        if not allowed_names:
            return requested_names

        filtered = [name for name in requested_names if name in allowed_names]
        if filtered:
            return filtered
        if requested_names:
            return allowed_names[:fallback_count]
        return allowed_names[:fallback_count]

    def _build_semantic_tool_args(
        self,
        semantic_binding: dict[str, Any],
        runtime_context: dict[str, Any],
    ) -> dict[str, Any]:
        model_name = str(semantic_binding.get("entry_model") or "").strip()
        model_metadata = self._lookup_model_metadata(model_name, runtime_context)
        metrics = self._sanitize_requested_fields(
            semantic_binding.get("metrics") or [],
            model_metadata.get("metrics") or [],
            fallback_count=4,
        )
        dimensions = self._sanitize_requested_fields(
            semantic_binding.get("dimensions") or [],
            model_metadata.get("dimensions") or [],
            fallback_count=4,
        )

        args = {
            "model_name": model_name,
            "dimensions": dimensions,
            "metrics": metrics,
            "entity_filters": dict(semantic_binding.get("entity_filters") or {}),
            "resolved_filters": dict(semantic_binding.get("resolved_filters") or {}),
            "grain": semantic_binding.get("grain"),
        }
        legacy_filters = semantic_binding.get("filters")
        if isinstance(legacy_filters, list) and legacy_filters:
            args["filters"] = legacy_filters
        return args

    def _build_mql_tool_args(
        self,
        semantic_binding: dict[str, Any],
        runtime_context: dict[str, Any],
    ) -> dict[str, Any]:
        model_name = str(semantic_binding.get("entry_model") or "").strip()
        model_metadata = self._lookup_model_metadata(model_name, runtime_context)
        metrics = self._sanitize_requested_fields(
            semantic_binding.get("metrics") or [],
            model_metadata.get("metrics") or [],
            fallback_count=4,
        )
        dimensions = self._sanitize_requested_fields(
            semantic_binding.get("dimensions") or [],
            model_metadata.get("dimensions") or [],
            fallback_count=4,
        )

        args = {
            "model_name": model_name,
            "select": [{"metric": metric} for metric in metrics],
            "group_by": dimensions,
            "entity_filters": dict(semantic_binding.get("entity_filters") or {}),
            "resolved_filters": dict(semantic_binding.get("resolved_filters") or {}),
            "filters": list(semantic_binding.get("filters") or []),
            "order": [],
            "limit": 100,
        }

        time_context = self._build_mql_time_context(semantic_binding, runtime_context)
        if time_context:
            args["time_context"] = time_context

        analysis_mode = semantic_binding.get("analysis_mode")
        if isinstance(analysis_mode, dict) and analysis_mode:
            args["analysis_mode"] = analysis_mode

        drilldown = semantic_binding.get("drilldown")
        if isinstance(drilldown, dict) and drilldown:
            args["drilldown"] = drilldown

        return args

    def _build_mql_time_context(
        self,
        semantic_binding: dict[str, Any],
        runtime_context: dict[str, Any],
    ) -> dict[str, Any]:
        explicit = semantic_binding.get("time_context")
        if isinstance(explicit, dict) and explicit:
            return dict(explicit)

        period_hints = runtime_context.get("period_hints") or {}
        grain = str(semantic_binding.get("grain") or "").strip()
        year = period_hints.get("year")
        quarter = period_hints.get("quarter")
        periods = [str(item) for item in (period_hints.get("periods") or []) if str(item or "").strip()]

        range_value = ""
        if year and quarter:
            range_value = f"{year}Q{quarter}"
        elif len(periods) == 1:
            range_value = periods[0]
        elif len(periods) > 1:
            range_value = f"{periods[0]}..{periods[-1]}"
        elif year:
            range_value = str(year)

        if not range_value and not grain:
            return {}

        payload: dict[str, Any] = {}
        if grain:
            payload["grain"] = grain
        if range_value:
            payload["range"] = range_value
        return payload

    def _select_tool_definitions(
        self,
        node: dict[str, Any],
        runtime_context: dict[str, Any],
    ) -> list[dict[str, Any]]:
        node_kind = str(node.get("kind") or "task")
        hints = [hint for hint in node.get("tool_hints") or [] if hint in TOOL_DEFINITION_MAP]
        query_mode = runtime_context.get("query_mode")
        semantic_binding = node.get("semantic_binding") if isinstance(node.get("semantic_binding"), dict) else {}
        has_semantic_binding = bool(semantic_binding.get("entry_model") or semantic_binding.get("models"))
        fallback_policy = str(semantic_binding.get("fallback_policy") or "").strip().lower()
        query_language = str(semantic_binding.get("query_language") or "").strip().lower()

        if node_kind == "schema":
            if hints and any(name != "metadata_query" for name in hints):
                allowed_names = hints
            else:
                allowed_names = ["metadata_query"]
        elif node_kind == "knowledge":
            allowed_names = ["knowledge_search"]
        elif node_kind == "visualization":
            allowed_names = ["chart_generator"]
        elif has_semantic_binding and (query_language == "tda_mql" or "mql_query" in hints):
            allowed_names = ["mql_query"]
        elif has_semantic_binding:
            allowed_names = ["semantic_query"]
            if fallback_policy not in {"none", "semantic_only"}:
                allowed_names.append("sql_executor")
            allowed_names.append("knowledge_search")
        elif hints:
            allowed_names = hints
        elif node_kind in {"query", "analysis"} and query_mode == "metadata":
            allowed_names = ["metadata_query"]
        elif node_kind in {"query", "analysis"}:
            allowed_names = ["semantic_query", "sql_executor", "knowledge_search"]
        else:
            allowed_names = list(TOOL_DEFINITION_MAP)

        if (
            node_kind in {"query", "analysis"}
            and query_mode != "metadata"
            and "metadata_query" in allowed_names
            and "metadata_query" not in hints
        ):
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
            "semantic_catalog_by_kind": runtime_context.get("semantic_catalog_by_kind"),
            "relevant_models": [
                {
                    "name": item.get("name"),
                    "label": item.get("label"),
                    "semantic_kind": item.get("semantic_kind"),
                    "semantic_domain": item.get("semantic_domain"),
                    "source_table": item.get("source_table"),
                    "has_yaml_definition": item.get("has_yaml_definition"),
                    "recommended_tool": item.get("recommended_tool"),
                }
                for item in (runtime_context.get("relevant_models") or [])[:6]
            ],
            "relevant_tables": (runtime_context.get("relevant_tables") or [])[:8],
            "execution_guidance": runtime_context.get("execution_guidance"),
        }
        return json.dumps(compact, ensure_ascii=False, indent=2)

    def _format_understanding_result(self, understanding_result: dict[str, Any] | None) -> str:
        if not understanding_result:
            return "none"
        compact = {
            "query_mode": understanding_result.get("query_mode"),
            "intent_summary": understanding_result.get("intent_summary"),
            "business_goal": understanding_result.get("business_goal"),
            "entities": understanding_result.get("entities"),
            "semantic_scope": understanding_result.get("semantic_scope"),
            "dimensions": understanding_result.get("dimensions"),
            "metrics": understanding_result.get("metrics"),
            "comparisons": understanding_result.get("comparisons"),
            "required_evidence": understanding_result.get("required_evidence"),
            "resolution_requirements": understanding_result.get("resolution_requirements"),
            "candidate_models": understanding_result.get("candidate_models"),
            "ambiguities": understanding_result.get("ambiguities"),
            "confidence": understanding_result.get("confidence"),
        }
        return json.dumps(compact, ensure_ascii=False, indent=2)

    def _format_semantic_binding(self, semantic_binding: Any) -> str:
        if not isinstance(semantic_binding, dict) or not semantic_binding:
            return "none"
        compact = {
            "entry_model": semantic_binding.get("entry_model"),
            "supporting_models": semantic_binding.get("supporting_models", []),
            "metrics": semantic_binding.get("metrics", []),
            "dimensions": semantic_binding.get("dimensions", []),
            "entity_filters": semantic_binding.get("entity_filters", {}),
            "resolved_filters": semantic_binding.get("resolved_filters", {}),
            "grain": semantic_binding.get("grain", ""),
            "query_language": semantic_binding.get("query_language", ""),
            "time_context": semantic_binding.get("time_context", {}),
            "analysis_mode": semantic_binding.get("analysis_mode", {}),
            "drilldown": semantic_binding.get("drilldown", {}),
            "fallback_policy": semantic_binding.get("fallback_policy", "atomic_then_sql"),
        }
        legacy_filters = semantic_binding.get("filters")
        if legacy_filters:
            compact["filters"] = legacy_filters
        return json.dumps(compact, ensure_ascii=False, indent=2)

    def _should_attempt_repair(self, raw_result: Any, tool_name: str) -> bool:
        return (
            tool_name in {"sql_executor", "semantic_query", "metadata_query"}
            and isinstance(raw_result, dict)
            and bool(raw_result.get("error"))
        )

    async def _attempt_tool_repair(
        self,
        *,
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
                trace={
                    "agent": "executor",
                    "operation": "tool_repair",
                    "node_id": node.get("id", ""),
                    "node_title": node.get("title", ""),
                },
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
                    thinking=thinking or f"Automatic repair failed for {error_message}",
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
                    error=f"Unknown tool: {repaired_tool_name}",
                )

            t0 = time.monotonic()
            repaired_result = await repaired_fn(**repaired_args)
            duration_ms = int((time.monotonic() - t0) * 1000)

            return ExecutionResult(
                node_id="",
                tool_name=repaired_tool_name,
                tool_args=repaired_args,
                raw_result=repaired_result,
                thinking=(thinking + "\n\nAutomatic repair retry executed.").strip(),
                duration_ms=duration_ms,
                error=str(repaired_result.get("error") or "") if isinstance(repaired_result, dict) else "",
            )
        except Exception as exc:
            return ExecutionResult(
                node_id="",
                thinking=f"Automatic repair failed: {exc}",
                error=error_message,
            )

    def _build_previous_summary(self, previous_results: dict[str, ExecutionResult]) -> str:
        if not previous_results:
            return ""

        lines: list[str] = []
        for node_id, result in previous_results.items():
            if result.error:
                lines.append(f"- {node_id}: failed - {result.error}")
                continue

            if result.tool_name:
                result_str = ""
                if isinstance(result.raw_result, dict):
                    if result.raw_result.get("row_count") is not None:
                        result_str = f"returned {result.raw_result['row_count']} rows"
                    elif result.raw_result.get("count") is not None:
                        result_str = f"{result.raw_result['count']} items"
                    elif result.raw_result.get("columns"):
                        result_str = f"{len(result.raw_result['columns'])} columns"
                lines.append(f"- {node_id}: {result.tool_name} -> {result_str or 'completed'}")
                continue

            lines.append(f"- {node_id}: {result.thinking[:60]}")

        return "\n".join(lines)
