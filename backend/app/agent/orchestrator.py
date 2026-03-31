"""Multi-agent orchestrator with StageGraph v1-lite."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import re
from typing import Any, AsyncGenerator

from app.agent.executor_agent_v2 import ExecutionResult, ExecutorAgent
from app.agent.plan_presentation import build_plan_metadata, plan_graph_signature
from app.agent.planner_agent_v2 import PlannerAgent
from app.agent.reviewer_agent_v2 import ReviewerAgent
from app.agent.runtime_context import build_runtime_context, build_runtime_status_text
from app.agent.semantic_grounding import build_semantic_grounding
from app.agent.stage_graph import StageGraphTracker
from app.agent.understanding_agent import UnderstandingAgent
from app.database import AsyncSessionLocal
from app.schemas.semantic import TdaMqlRequest
from app.semantic.compiler_v2 import SemanticDefinitionError
from app.semantic.mql import compile_tda_mql_request
from pydantic import ValidationError


MAX_REPLAN_ATTEMPTS = 2
MAX_TOTAL_STEPS = 40


@dataclass
class AgentEvent:
    type: str
    agent: str
    content: str
    step_number: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    is_final: bool = False
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "agent": self.agent,
            "step_number": self.step_number,
            "content": self.content,
            "metadata": self.metadata,
            "is_final": self.is_final,
            "timestamp": self.timestamp,
        }


def _topological_sort(plan_graph: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = plan_graph.get("nodes", [])
    if not nodes:
        return []

    node_map = {node["id"]: node for node in nodes}
    visited: set[str] = set()
    result: list[dict[str, Any]] = []

    def visit(node_id: str) -> None:
        if node_id in visited:
            return
        visited.add(node_id)
        node = node_map.get(node_id)
        if not node:
            return
        for dep_id in node.get("depends_on", []):
            visit(dep_id)
        result.append(node)

    for node in nodes:
        visit(node["id"])

    return result


def _build_stage_event(
    stage_graph: StageGraphTracker,
    *,
    stage_id: str,
    stage_status: str,
    content: str,
    step_number: int,
    metadata: dict[str, Any] | None = None,
    stage_reasoning: list[str] | None = None,
    is_final: bool = False,
) -> AgentEvent:
    event_metadata = {
        "stage_id": stage_id,
        "stage_status": stage_status,
        "stage_graph": stage_graph.snapshot(),
    }
    if stage_reasoning:
        event_metadata["stage_reasoning"] = [str(item) for item in stage_reasoning if str(item or "").strip()]
    if metadata:
        event_metadata.update(metadata)
    return AgentEvent(
        type="stage_update",
        agent="orchestrator",
        content=content,
        step_number=step_number,
        metadata=event_metadata,
        is_final=is_final,
    )


def _node_requires_drilldown(node: dict[str, Any]) -> bool:
    binding = node.get("semantic_binding") if isinstance(node.get("semantic_binding"), dict) else {}
    drilldown = binding.get("drilldown") if isinstance(binding.get("drilldown"), dict) else {}
    return bool(drilldown.get("enabled"))


def _build_tda_mql_draft_metadata(
    runtime_context: dict[str, Any],
    understanding_result: dict[str, Any],
) -> dict[str, Any]:
    relevant_models = runtime_context.get("relevant_models") or []
    model = relevant_models[0] if relevant_models else {}
    period_hints = runtime_context.get("period_hints") or {}

    grain = str((model.get("time") or {}).get("grain") or "").strip()
    if not grain:
        grain = "month" if period_hints.get("periods") else ("year" if period_hints.get("year") else "")

    range_value = ""
    if period_hints.get("year") and period_hints.get("quarter"):
        range_value = f"{period_hints['year']}Q{period_hints['quarter']}"
    elif len(period_hints.get("periods") or []) == 1:
        range_value = str(period_hints["periods"][0])
    elif len(period_hints.get("periods") or []) > 1:
        periods = [str(item) for item in period_hints.get("periods") or []]
        range_value = f"{periods[0]}..{periods[-1]}"
    elif period_hints.get("year"):
        range_value = str(period_hints["year"])

    compare_hint = ""
    comparisons = understanding_result.get("comparisons") or []
    if comparisons:
        first = comparisons[0]
        if isinstance(first, dict):
            compare_hint = str(first.get("mode") or first.get("label") or "").strip()
        else:
            compare_hint = str(first).strip()

    metadata = {
        "entry_model": model.get("name"),
        "query_language": "tda_mql" if model.get("recommended_tool") == "mql_query" else "",
        "metrics": list(understanding_result.get("metrics") or []),
        "dimensions": list(understanding_result.get("dimensions") or []),
        "time_context": {
            "grain": grain,
            "range": range_value,
        },
    }
    if compare_hint:
        metadata["time_context"]["compare"] = compare_hint
    return metadata


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _unique_strings(values: list[Any]) -> list[str]:
    result: list[str] = []
    for item in values:
        text = _clean_text(item)
        if text and text not in result:
            result.append(text)
    return result


def _format_model_label(model: dict[str, Any]) -> dict[str, str]:
    name = _clean_text(model.get("name"))
    label = _clean_text(model.get("label"))
    display_name = f"{label} ({name})" if label and name and label != name else (label or name)
    return {
        "name": name,
        "label": label,
        "display_name": display_name,
    }


def _normalize_term_records(
    terms: list[Any],
) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    seen: set[str] = set()

    for item in terms:
        if isinstance(item, dict):
            name = _clean_text(item.get("name") or item.get("column"))
            label = _clean_text(item.get("label"))
        else:
            text = _clean_text(item)
            name = text
            label = ""

        key = name or label
        if not key or key in seen:
            continue
        seen.add(key)
        display_name = f"{name} ({label})" if name and label and name != label else (label or name)
        records.append(
            {
                "name": name,
                "label": label,
                "display_name": display_name,
            }
        )
    return records


def _get_model_term_records(model: dict[str, Any], *, key: str) -> list[dict[str, str]]:
    explicit = model.get(key)
    if isinstance(explicit, list) and explicit:
        return _normalize_term_records(explicit)

    if key == "metric_terms":
        return _normalize_term_records(model.get("metrics") or [])
    if key == "dimension_terms":
        return _normalize_term_records(model.get("dimensions") or [])
    return []


def _normalize_match_text(value: Any) -> str:
    text = _clean_text(value).lower()
    if not text:
        return ""
    return "".join(
        char
        for char in text
        if char.isalnum() or char == "_" or "\u4e00" <= char <= "\u9fff"
    )


def _build_query_fragments(user_query: str) -> list[str]:
    normalized_query = _normalize_match_text(user_query)
    if not normalized_query:
        return []

    raw_fragments = re.split(
        r"[，。；;、\s]+|(?:并且|以及|然后|同时|和|与)",
        user_query or "",
    )
    fragments: list[str] = [normalized_query]
    for item in raw_fragments:
        normalized = _normalize_match_text(item)
        if len(normalized) >= 2 and normalized not in fragments:
            fragments.append(normalized)
    return fragments

def _bigram_overlap_score(left: str, right: str) -> int:
    if len(left) < 2 or len(right) < 2:
        return 0
    left_bigrams = {left[idx : idx + 2] for idx in range(len(left) - 1)}
    right_bigrams = {right[idx : idx + 2] for idx in range(len(right) - 1)}
    return len(left_bigrams & right_bigrams)


def _term_aliases(term_record: dict[str, Any]) -> list[str]:
    aliases: list[str] = []
    for key in ("name", "label", "display_name"):
        normalized = _normalize_match_text(term_record.get(key))
        if normalized and normalized not in aliases:
            aliases.append(normalized)
    return aliases


def _score_term_record(term_record: dict[str, Any], fragments: list[str]) -> int:
    aliases = _term_aliases(term_record)
    if not aliases:
        return 0

    wants_count = any(
        any(keyword in fragment for keyword in ("数量", "个数", "笔数", "单据数", "count"))
        for fragment in fragments
    )
    if not wants_count and any("count" in alias or alias.endswith("数") for alias in aliases):
        return 0

    best_score = 0
    for alias in aliases:
        for fragment in fragments:
            if len(fragment) < 2:
                continue
            score = 0
            if fragment in alias or alias in fragment:
                score += 12 + min(len(fragment), 6)
            score += min(_bigram_overlap_score(fragment, alias) * 3, 9)
            best_score = max(best_score, score)
        if "差异" in alias and any("差异" in fragment for fragment in fragments):
            best_score += 8
        if "金额" in alias and any("金额" in fragment for fragment in fragments):
            best_score += 4
        if "税基" in alias and any("税基" in fragment for fragment in fragments):
            best_score += 5
        if "账面" in alias and any("账面" in fragment for fragment in fragments):
            best_score += 5
        if "收入" in alias and any("收入" in fragment for fragment in fragments):
            best_score += 4
        if "状态" in alias and any("状态" in fragment for fragment in fragments):
            best_score += 4
        if "所属期" in alias and any("所属期" in fragment for fragment in fragments):
            best_score += 4
    return best_score

def _select_term_records(
    term_records: list[dict[str, str]],
    *,
    requested_names: list[str],
    user_query: str,
    limit: int,
) -> list[dict[str, str]]:
    if not term_records:
        return []

    if requested_names:
        requested_lookup = {_normalize_match_text(name) for name in requested_names if _normalize_match_text(name)}
        selected = [
            item
            for item in term_records
            if _normalize_match_text(item.get("name")) in requested_lookup
            or _normalize_match_text(item.get("label")) in requested_lookup
        ]
        if selected:
            return selected[:limit]

    fragments = _build_query_fragments(user_query)
    if not fragments:
        return []

    scored: list[tuple[int, int, dict[str, str]]] = []
    for index, item in enumerate(term_records):
        score = _score_term_record(item, fragments)
        if score > 0:
            scored.append((score, index, item))

    scored.sort(key=lambda record: (-record[0], record[1]))
    selected = [item for _, _, item in scored[:limit]]

    def append_first(predicate: Any) -> None:
        if len(selected) >= limit:
            return
        selected_names = {_clean_text(item.get("name")) for item in selected}
        for item in term_records:
            name = _clean_text(item.get("name"))
            if not name or name in selected_names:
                continue
            aliases = _term_aliases(item)
            if predicate(aliases):
                selected.append(item)
                selected_names.add(name)
                return

    if any("差异" in fragment for fragment in fragments):
        append_first(lambda aliases: any("差异" in alias for alias in aliases))
    if any("税基" in fragment for fragment in fragments):
        append_first(lambda aliases: any("税基" in alias for alias in aliases))
    if any("账面" in fragment for fragment in fragments) and any("收入" in fragment for fragment in fragments):
        append_first(lambda aliases: any("账面" in alias and "收入" in alias for alias in aliases))
    if any("折扣" in fragment for fragment in fragments) and any("单" in fragment for fragment in fragments):
        append_first(lambda aliases: any("折扣" in alias and "单" in alias and "号" in alias for alias in aliases))

    return selected[:limit]

def _build_semantic_binding_stage_payload(
    runtime_context: dict[str, Any],
    understanding_result: dict[str, Any],
    user_query: str,
) -> dict[str, Any]:
    relevant_models = [item for item in (runtime_context.get("relevant_models") or []) if isinstance(item, dict)]
    entry_model = relevant_models[0] if relevant_models else {}
    entry_model_name = _clean_text(entry_model.get("name"))

    metric_terms = _get_model_term_records(entry_model, key="metric_terms")
    dimension_terms = _get_model_term_records(entry_model, key="dimension_terms")
    detail_terms = _normalize_term_records(entry_model.get("detail_fields") or [])

    requested_metric_names = _unique_strings(understanding_result.get("metrics") or [])
    requested_dimension_names = _unique_strings(understanding_result.get("dimensions") or [])
    selected_metrics = _select_term_records(
        metric_terms,
        requested_names=requested_metric_names,
        user_query=user_query,
        limit=8,
    )
    selected_dimensions = _select_term_records(
        dimension_terms,
        requested_names=requested_dimension_names,
        user_query=user_query,
        limit=8,
    )

    enterprise_names = _unique_strings(
        (understanding_result.get("entities") or {}).get("enterprise_names") or []
        + [item.get("enterprise_name") for item in (runtime_context.get("enterprise_candidates") or [])]
    )
    taxpayer_ids = _unique_strings(
        (understanding_result.get("entities") or {}).get("taxpayer_ids") or []
        + [item.get("taxpayer_id") for item in (runtime_context.get("enterprise_candidates") or [])]
    )
    entity_filters: dict[str, list[str]] = {}
    if enterprise_names:
        entity_filters["enterprise_name"] = enterprise_names[:5]

    resolved_filters: dict[str, list[str]] = {}
    if taxpayer_ids and not entity_filters:
        resolved_filters["taxpayer_id"] = taxpayer_ids[:5]

    period_hints = runtime_context.get("period_hints") or {}
    periods = _unique_strings(period_hints.get("periods") or [])
    time_context: dict[str, Any] = {}
    if period_hints.get("year") and period_hints.get("quarter"):
        time_context["range"] = f"{period_hints['year']}Q{period_hints['quarter']}"
    elif len(periods) == 1:
        time_context["range"] = periods[0]
    elif len(periods) > 1:
        time_context["range"] = f"{periods[0]}..{periods[-1]}"
    elif period_hints.get("year"):
        time_context["range"] = str(period_hints["year"])

    grain = _clean_text((entry_model.get("time") or {}).get("grain"))
    if not grain:
        grain = "month" if periods else ("year" if period_hints.get("year") else "")
    if grain:
        time_context["grain"] = grain

    candidate_models = []
    for model in relevant_models[:6]:
        model_labels = _format_model_label(model)
        candidate_models.append(
            {
                **model_labels,
                "semantic_kind": _clean_text(model.get("semantic_kind")),
                "recommended_tool": _clean_text(model.get("recommended_tool")),
                "metric_terms": _get_model_term_records(model, key="metric_terms"),
                "dimension_terms": _get_model_term_records(model, key="dimension_terms"),
                "detail_fields": _normalize_term_records(model.get("detail_fields") or []),
            }
        )

    query_language = "tda_mql" if _clean_text(entry_model.get("recommended_tool")) == "mql_query" else ""
    semantic_binding = {
        "entry_model": entry_model_name,
        "metrics": [item["name"] for item in selected_metrics if item.get("name")],
        "dimensions": [item["name"] for item in selected_dimensions if item.get("name")],
        "detail_fields": [item["name"] for item in detail_terms if item.get("name")],
        "entity_filters": entity_filters,
        "resolved_filters": resolved_filters,
        "query_language": query_language,
        "time_context": time_context,
    }

    return {
        "entry_model": _format_model_label(entry_model),
        "candidate_models": candidate_models,
        "metrics": selected_metrics,
        "dimensions": selected_dimensions,
        "detail_fields": detail_terms,
        "entity_filters": entity_filters,
        "resolved_filters": resolved_filters,
        "query_language": query_language,
        "time_context": time_context,
        "semantic_binding": semantic_binding,
    }


def _build_tda_mql_draft_payload(
    draft_metadata: dict[str, Any],
    binding_payload: dict[str, Any],
) -> dict[str, Any]:
    binding = binding_payload.get("semantic_binding") if isinstance(binding_payload.get("semantic_binding"), dict) else {}
    metrics = _unique_strings(binding.get("metrics") or draft_metadata.get("metrics") or [])
    dimensions = _unique_strings(binding.get("dimensions") or draft_metadata.get("dimensions") or [])

    payload: dict[str, Any] = {
        "model_name": _clean_text(binding.get("entry_model") or draft_metadata.get("entry_model")),
        "select": [{"metric": metric} for metric in metrics],
        "group_by": dimensions,
        "entity_filters": dict(binding.get("entity_filters") or {}),
        "resolved_filters": dict(binding.get("resolved_filters") or {}),
        "filters": [],
        "order": [],
        "limit": 100,
    }

    time_context = binding.get("time_context") or draft_metadata.get("time_context") or {}
    if isinstance(time_context, dict) and time_context:
        payload["time_context"] = dict(time_context)
    return payload


def _build_tda_mql_validation_metadata(compiled: dict[str, Any]) -> dict[str, Any]:
    return {
        "semantic_query": dict(compiled.get("semantic_query") or {}),
        "unsupported_features": list(compiled.get("unsupported_features") or []),
        "relationship_graph_count": len(compiled.get("relationship_graph") or []),
        "metric_lineage_count": len(compiled.get("metric_lineage") or []),
        "detail_field_count": len(compiled.get("detail_fields") or []),
        "query_hints": dict(compiled.get("query_hints") or {}),
    }


async def _validate_tda_mql_draft_payload(payload: dict[str, Any]) -> dict[str, Any]:
    request = TdaMqlRequest.model_validate(payload)
    async with AsyncSessionLocal() as db:
        compiled = await compile_tda_mql_request(request, db)

    unsupported_features = list(compiled.get("unsupported_features") or [])
    if unsupported_features:
        raise SemanticDefinitionError(
            "TDA-MQL 草拟包含当前阶段不支持的能力: " + ", ".join(unsupported_features)
        )

    return {
        "validated_request": request.model_dump(exclude_none=True),
        "validation": _build_tda_mql_validation_metadata(compiled),
    }


def _compact_semantic_binding_for_snapshot(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        "entry_model": _clean_text(value.get("entry_model")),
        "metrics": _unique_strings(value.get("metrics") or [])[:8],
        "dimensions": _unique_strings(value.get("dimensions") or [])[:8],
        "query_language": _clean_text(value.get("query_language")),
    }


def _build_planning_snapshot(plan_graph: dict[str, Any]) -> dict[str, Any]:
    nodes = []
    for node in plan_graph.get("nodes", []):
        if not isinstance(node, dict):
            continue
        nodes.append(
            {
                "id": _clean_text(node.get("id")),
                "title": _clean_text(node.get("title")),
                "detail": _clean_text(node.get("detail")),
                "status": _clean_text(node.get("status")),
                "kind": _clean_text(node.get("kind")),
                "depends_on": _unique_strings(node.get("depends_on") or []),
                "tool_hints": _unique_strings(node.get("tool_hints") or []),
                "semantic_binding": _compact_semantic_binding_for_snapshot(node.get("semantic_binding")),
            }
        )
    return {
        "title": _clean_text(plan_graph.get("title")),
        "summary": _clean_text(plan_graph.get("summary")),
        "active_node_ids": _unique_strings(plan_graph.get("active_node_ids") or []),
        "nodes": nodes,
    }


def _build_feasibility_assessment(
    runtime_context: dict[str, Any],
    understanding_result: dict[str, Any],
) -> tuple[bool, str, dict[str, Any]]:
    relevant_models = runtime_context.get("relevant_models") or []
    enterprise_names = (understanding_result.get("entities") or {}).get("enterprise_names") or []
    enterprise_candidates = runtime_context.get("enterprise_candidates") or []
    resolution_ready = not enterprise_names or bool(enterprise_candidates)

    metadata = {
        "relevant_model_count": len(relevant_models),
        "resolution_ready": resolution_ready,
        "recommended_tools": [
            str(item.get("recommended_tool") or "").strip()
            for item in relevant_models
            if str(item.get("recommended_tool") or "").strip()
        ],
    }

    if not relevant_models:
        return False, "No executable semantic assets were matched.", metadata
    if enterprise_names and not enterprise_candidates:
        return False, "Enterprise entities are unresolved, so controlled execution cannot continue.", metadata

    return True, "Semantic assets, entity resolution, and execution constraints are all ready.", metadata


def _partition_execution_nodes(
    plan_graph: dict[str, Any],
    execution_results: dict[str, ExecutionResult],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    metric_nodes: list[dict[str, Any]] = []
    detail_nodes: list[dict[str, Any]] = []

    for node in _topological_sort(plan_graph):
        if node.get("status") == "completed" or node.get("id") in execution_results:
            continue
        if node.get("kind") in {"goal", "answer"}:
            continue
        if _node_requires_drilldown(node):
            detail_nodes.append(node)
        else:
            metric_nodes.append(node)

    return metric_nodes, detail_nodes


def _build_evidence_verification(
    plan_graph: dict[str, Any],
    execution_results: dict[str, ExecutionResult],
) -> tuple[str, dict[str, Any]]:
    query_nodes = [
        node for node in plan_graph.get("nodes", [])
        if node.get("kind") in {"query", "analysis"} and node.get("id") in execution_results
    ]
    result_rows = 0
    compare_nodes: list[str] = []
    error_nodes: list[str] = []
    detail_nodes: list[str] = []

    for node in query_nodes:
        node_id = node["id"]
        result = execution_results[node_id]
        raw_result = result.raw_result if isinstance(result.raw_result, dict) else {}
        result_rows += int(raw_result.get("row_count") or 0)
        if raw_result.get("compare"):
            compare_nodes.append(node_id)
        if _node_requires_drilldown(node):
            detail_nodes.append(node_id)
        if result.error:
            error_nodes.append(node_id)

    note = f"Validated {len(query_nodes)} query/analysis nodes with {result_rows} evidence rows in total."
    metadata = {
        "reviewable_node_count": len(query_nodes),
        "total_row_count": result_rows,
        "compare_node_ids": compare_nodes,
        "detail_node_ids": detail_nodes,
        "error_node_ids": error_nodes,
    }
    return note, metadata


class MultiAgentOrchestrator:
    def __init__(self, llm: Any):
        self.llm = llm
        self.understanding = UnderstandingAgent(llm)
        self.planner = PlannerAgent(llm)
        self.executor = ExecutorAgent(llm)
        self.reviewer = ReviewerAgent(llm)
        self.conversation_history: list[dict[str, str]] = []

    async def run(self, user_query: str) -> AsyncGenerator[AgentEvent, None]:
        step = 0
        stage_graph = StageGraphTracker()
        current_stage_id = ""
        stage_reasoning: dict[str, list[str]] = {}
        llm_call_traces: list[dict[str, Any]] = []
        stage_llm_traces: dict[str, list[dict[str, Any]]] = {}
        llm_trace_cursor = 0
        llm_trace_tokens: tuple[Any, Any, Any] | None = None

        if hasattr(self.llm, "begin_trace") and callable(getattr(self.llm, "begin_trace")):
            try:
                llm_trace_tokens = self.llm.begin_trace(
                    llm_call_traces,
                    meta_provider=lambda: {"stage_id": current_stage_id},
                )
            except Exception:
                llm_trace_tokens = None

        def next_step() -> int:
            nonlocal step
            current = step
            step += 1
            return current

        def append_stage_reasoning(stage_id: str, text: str) -> None:
            note = _clean_text(text)
            if not stage_id or not note:
                return
            bucket = stage_reasoning.setdefault(stage_id, [])
            if note in bucket:
                return
            bucket.append(note)
            if len(bucket) > 12:
                del bucket[:-12]

        def pull_new_llm_traces() -> list[dict[str, Any]]:
            nonlocal llm_trace_cursor
            pulled: list[dict[str, Any]] = []
            while llm_trace_cursor < len(llm_call_traces):
                raw_trace = llm_call_traces[llm_trace_cursor]
                llm_trace_cursor += 1

                stage_id = _clean_text(raw_trace.get("stage_id")) or current_stage_id or "unknown"
                compact_trace = {
                    "llm_call_index": int(raw_trace.get("llm_call_index") or len(stage_llm_traces.get(stage_id, [])) + 1),
                    "timestamp": _clean_text(raw_trace.get("timestamp")),
                    "agent": _clean_text(raw_trace.get("agent")),
                    "operation": _clean_text(raw_trace.get("operation")),
                    "node_id": _clean_text(raw_trace.get("node_id")),
                    "node_title": _clean_text(raw_trace.get("node_title")),
                    "model": _clean_text(raw_trace.get("model")),
                    "thinking": _clean_text(raw_trace.get("thinking")),
                    "raw_content_preview": _clean_text(raw_trace.get("raw_content_preview")),
                    "user_prompt_preview": _clean_text(raw_trace.get("user_prompt_preview")),
                }
                bucket = stage_llm_traces.setdefault(stage_id, [])
                bucket.append(compact_trace)
                if len(bucket) > 40:
                    del bucket[:-40]

                append_stage_reasoning(stage_id, compact_trace.get("thinking", ""))
                pulled.append(compact_trace)
            return pulled

        def sync_llm_traces() -> None:
            pull_new_llm_traces()

        def llm_trace_to_thinking_content(trace: dict[str, Any]) -> str:
            parts = []
            if _clean_text(trace.get("agent")):
                parts.append(_clean_text(trace.get("agent")))
            if _clean_text(trace.get("operation")):
                parts.append(_clean_text(trace.get("operation")))
            if _clean_text(trace.get("node_title")):
                parts.append(_clean_text(trace.get("node_title")))
            prefix = f"LLM#{trace.get('llm_call_index')}" if trace.get("llm_call_index") else "LLM"
            title = " / ".join(parts)
            body = _clean_text(trace.get("thinking")) or _clean_text(trace.get("raw_content_preview"))
            if title and body:
                return f"{prefix} [{title}] {body}"
            if title:
                return f"{prefix} [{title}]"
            return f"{prefix} {body}".strip()

        def build_thinking_event_from_trace(trace: dict[str, Any]) -> AgentEvent:
            stage_id = _clean_text(trace.get("stage_id")) or current_stage_id
            metadata = {
                "llm_trace": True,
                "llm_trace_item": trace,
                "llm_call_index": trace.get("llm_call_index"),
                "operation": trace.get("operation"),
                "node_id": trace.get("node_id"),
                "node_title": trace.get("node_title"),
            }
            if stage_id:
                metadata["stage_id"] = stage_id
                try:
                    metadata["stage_status"] = stage_graph.current_status(stage_id)
                except Exception:
                    pass
            return AgentEvent(
                type="thinking",
                agent=_clean_text(trace.get("agent")) or "orchestrator",
                content=llm_trace_to_thinking_content(trace),
                step_number=next_step(),
                metadata=current_stage_metadata(metadata),
            )

        def emit_new_llm_trace_events() -> list[AgentEvent]:
            events: list[AgentEvent] = []
            for trace in pull_new_llm_traces():
                events.append(build_thinking_event_from_trace(trace))
            return events

        def finalize_llm_trace() -> None:
            nonlocal llm_trace_tokens
            sync_llm_traces()
            if llm_trace_tokens is None:
                return
            if hasattr(self.llm, "end_trace") and callable(getattr(self.llm, "end_trace")):
                try:
                    self.llm.end_trace(llm_trace_tokens)
                except Exception:
                    pass
            llm_trace_tokens = None

        def current_stage_metadata(metadata: dict[str, Any] | None = None) -> dict[str, Any]:
            event_metadata = dict(metadata or {})
            if current_stage_id and "stage_id" not in event_metadata:
                event_metadata["stage_id"] = current_stage_id
                event_metadata["stage_status"] = stage_graph.current_status(current_stage_id)
            return event_metadata

        def emit_event(
            *,
            type: str,
            agent: str,
            content: str,
            metadata: dict[str, Any] | None = None,
            is_final: bool = False,
        ) -> AgentEvent:
            return AgentEvent(
                type=type,
                agent=agent,
                content=content,
                step_number=next_step(),
                metadata=current_stage_metadata(metadata),
                is_final=is_final,
            )

        def emit_stage_event(
            *,
            stage_id: str,
            stage_status: str,
            content: str,
            metadata: dict[str, Any] | None = None,
            is_final: bool = False,
        ) -> AgentEvent:
            sync_llm_traces()
            stage_metadata = dict(metadata or {})
            traces = stage_llm_traces.get(stage_id, [])
            stage_metadata["stage_llm_traces"] = traces
            stage_metadata["stage_llm_call_count"] = len(traces)
            return _build_stage_event(
                stage_graph,
                stage_id=stage_id,
                stage_status=stage_status,
                content=content,
                step_number=next_step(),
                metadata=stage_metadata,
                stage_reasoning=stage_reasoning.get(stage_id, []),
                is_final=is_final,
            )

        yield emit_event(type="agent_start", agent="orchestrator", content="Preparing StageGraph v1-lite flow.")

        current_stage_id = "intent_recognition"
        stage_graph.mark_in_progress(current_stage_id, note="Extracting intent, entities, and time context.")
        yield emit_stage_event(
            stage_id=current_stage_id,
            stage_status="in_progress",
            content="StageGraph v1-lite: intent recognition started.",
        )

        semantic_grounding = await build_semantic_grounding(user_query)
        understanding = await self.understanding.understand(
            user_query,
            self.conversation_history,
            semantic_grounding,
        )
        for trace_event in emit_new_llm_trace_events():
            yield trace_event
        understanding_result = understanding.to_dict()

        intent_note = str(understanding_result.get("intent_summary") or "Intent understanding completed.")
        append_stage_reasoning(current_stage_id, intent_note)
        stage_graph.mark_completed(
            current_stage_id,
            note=intent_note,
            metadata={"understanding_result": understanding_result},
        )
        yield emit_stage_event(
            stage_id=current_stage_id,
            stage_status="completed",
            content="StageGraph v1-lite: intent recognition completed.",
            metadata={"understanding_result": understanding_result},
        )

        current_stage_id = "semantic_binding"
        stage_graph.mark_in_progress(current_stage_id, note="Binding semantic models, terms, and entity filters.")
        yield emit_stage_event(
            stage_id=current_stage_id,
            stage_status="in_progress",
            content="StageGraph v1-lite: semantic binding started.",
        )

        runtime_context = await build_runtime_context(
            user_query,
            understanding_result=understanding_result,
            semantic_grounding=semantic_grounding,
        )
        runtime_status_text = build_runtime_status_text(runtime_context)

        semantic_binding_payload = _build_semantic_binding_stage_payload(runtime_context, understanding_result, user_query)
        append_stage_reasoning(current_stage_id, runtime_status_text)
        stage_graph.mark_completed(
            current_stage_id,
            note=runtime_status_text,
            metadata={
                "runtime_context": runtime_context,
                "semantic_binding_display": semantic_binding_payload,
                "semantic_binding": semantic_binding_payload.get("semantic_binding"),
            },
        )
        yield emit_stage_event(
            stage_id=current_stage_id,
            stage_status="completed",
            content="StageGraph v1-lite: semantic binding completed.",
            metadata={
                "runtime_context": runtime_context,
                "semantic_binding_display": semantic_binding_payload,
                "semantic_binding": semantic_binding_payload.get("semantic_binding"),
                "stage_payload": semantic_binding_payload,
            },
        )

        current_stage_id = "tda_mql_draft"
        stage_graph.mark_in_progress(current_stage_id, note="Drafting TDA-MQL skeleton and semantic constraints.")
        yield emit_stage_event(
            stage_id=current_stage_id,
            stage_status="in_progress",
            content="StageGraph v1-lite: TDA-MQL draft started.",
            metadata={
                "semantic_binding_display": semantic_binding_payload,
                "semantic_binding": semantic_binding_payload.get("semantic_binding"),
            },
        )

        draft_metadata = _build_tda_mql_draft_metadata(runtime_context, understanding_result)
        tda_mql_draft_payload = _build_tda_mql_draft_payload(draft_metadata, semantic_binding_payload)
        try:
            draft_validation = await _validate_tda_mql_draft_payload(tda_mql_draft_payload)
        except (ValidationError, SemanticDefinitionError) as exc:
            draft_failure_note = f"TDA-MQL draft validation failed: {exc}"
            append_stage_reasoning(current_stage_id, draft_failure_note)
            stage_graph.mark_blocked(
                current_stage_id,
                note=draft_failure_note,
                metadata={
                    **draft_metadata,
                    "semantic_binding_display": semantic_binding_payload,
                    "semantic_binding": semantic_binding_payload.get("semantic_binding"),
                    "tda_mql_draft": tda_mql_draft_payload,
                    "validation_error": str(exc),
                },
            )
            yield emit_stage_event(
                stage_id=current_stage_id,
                stage_status="blocked",
                content="StageGraph v1-lite: TDA-MQL draft validation failed.",
                metadata={
                    **draft_metadata,
                    "semantic_binding_display": semantic_binding_payload,
                    "semantic_binding": semantic_binding_payload.get("semantic_binding"),
                    "tda_mql_draft": tda_mql_draft_payload,
                    "validation_error": str(exc),
                    "stage_payload": {
                        **semantic_binding_payload,
                        "tda_mql_draft": tda_mql_draft_payload,
                    },
                },
            )
            yield emit_event(
                type="error",
                agent="orchestrator",
                content=draft_failure_note,
                metadata={"stage_graph": stage_graph.snapshot(), "validation_error": str(exc)},
                is_final=True,
            )
            finalize_llm_trace()
            return
        except Exception as exc:
            draft_failure_note = f"TDA-MQL draft validation crashed: {type(exc).__name__}"
            append_stage_reasoning(current_stage_id, draft_failure_note)
            stage_graph.mark_blocked(
                current_stage_id,
                note=draft_failure_note,
                metadata={
                    **draft_metadata,
                    "semantic_binding_display": semantic_binding_payload,
                    "semantic_binding": semantic_binding_payload.get("semantic_binding"),
                    "tda_mql_draft": tda_mql_draft_payload,
                    "validation_error": type(exc).__name__,
                },
            )
            yield emit_stage_event(
                stage_id=current_stage_id,
                stage_status="blocked",
                content="StageGraph v1-lite: TDA-MQL draft validation failed.",
                metadata={
                    **draft_metadata,
                    "semantic_binding_display": semantic_binding_payload,
                    "semantic_binding": semantic_binding_payload.get("semantic_binding"),
                    "tda_mql_draft": tda_mql_draft_payload,
                    "validation_error": type(exc).__name__,
                },
            )
            yield emit_event(
                type="error",
                agent="orchestrator",
                content=draft_failure_note,
                metadata={"stage_graph": stage_graph.snapshot(), "validation_error": type(exc).__name__},
                is_final=True,
            )
            finalize_llm_trace()
            return

        draft_note = "TDA-MQL draft generated and validated for this turn."
        append_stage_reasoning(current_stage_id, draft_note)
        stage_graph.mark_completed(
            current_stage_id,
            note=draft_note,
            metadata={
                **draft_metadata,
                "semantic_binding_display": semantic_binding_payload,
                "semantic_binding": semantic_binding_payload.get("semantic_binding"),
                "tda_mql_draft": draft_validation["validated_request"],
                "tda_mql_validation": draft_validation["validation"],
            },
        )
        yield emit_stage_event(
            stage_id=current_stage_id,
            stage_status="completed",
            content="StageGraph v1-lite: TDA-MQL draft completed.",
            metadata={
                **draft_metadata,
                "semantic_binding_display": semantic_binding_payload,
                "semantic_binding": semantic_binding_payload.get("semantic_binding"),
                "tda_mql_draft": draft_validation["validated_request"],
                "tda_mql_validation": draft_validation["validation"],
                "stage_payload": {
                    **semantic_binding_payload,
                    "tda_mql_draft": draft_validation["validated_request"],
                    "tda_mql_validation": draft_validation["validation"],
                },
            },
        )

        current_stage_id = "feasibility_assessment"
        stage_graph.mark_in_progress(current_stage_id, note="Assessing feasibility and runtime constraints.")
        yield emit_stage_event(
            stage_id=current_stage_id,
            stage_status="in_progress",
            content="StageGraph v1-lite: feasibility assessment started.",
        )

        feasible, feasibility_note, feasibility_metadata = _build_feasibility_assessment(runtime_context, understanding_result)
        if not feasible:
            append_stage_reasoning(current_stage_id, feasibility_note)
            stage_graph.mark_blocked(
                current_stage_id,
                note=feasibility_note,
                metadata=feasibility_metadata,
            )
            yield emit_stage_event(
                stage_id=current_stage_id,
                stage_status="blocked",
                content="StageGraph v1-lite: feasibility assessment failed.",
                metadata=feasibility_metadata,
            )
            yield emit_event(
                type="error",
                agent="orchestrator",
                content=feasibility_note,
                metadata={"stage_graph": stage_graph.snapshot()},
                is_final=True,
            )
            finalize_llm_trace()
            return

        append_stage_reasoning(current_stage_id, feasibility_note)
        stage_graph.mark_completed(
            current_stage_id,
            note=feasibility_note,
            metadata=feasibility_metadata,
        )
        yield emit_stage_event(
            stage_id=current_stage_id,
            stage_status="completed",
            content="StageGraph v1-lite: feasibility assessment completed.",
            metadata=feasibility_metadata,
        )

        yield emit_event(
            type="status",
            agent="orchestrator",
            content=runtime_status_text,
            metadata={
                "runtime_context": runtime_context,
                "understanding_result": understanding_result,
                "semantic_grounding": semantic_grounding,
            },
        )

        current_stage_id = "planning"
        stage_graph.mark_in_progress(current_stage_id, note="Planner is generating an executable plan.")
        yield emit_stage_event(
            stage_id=current_stage_id,
            stage_status="in_progress",
            content="StageGraph v1-lite: planning started.",
        )

        yield emit_event(type="agent_start", agent="planner", content="Planner is generating the execution plan.")
        plan_result = await self.planner.plan(
            user_query,
            self.conversation_history,
            runtime_context,
            understanding_result=understanding_result,
        )
        for trace_event in emit_new_llm_trace_events():
            yield trace_event
        plan_graph = plan_result.graph

        if plan_result.reasoning:
            append_stage_reasoning(current_stage_id, plan_result.reasoning)
            yield emit_event(
                type="thinking",
                agent="planner",
                content=plan_result.reasoning,
                metadata={"reasoning": plan_result.reasoning},
            )

        if plan_result.source != "llm" or plan_graph.get("source") != "llm":
            plan_failure_note = "Planner failed to produce a real LLM plan."
            append_stage_reasoning(current_stage_id, plan_failure_note)
            stage_graph.mark_blocked(
                current_stage_id,
                note=plan_failure_note,
                metadata={"plan_source": plan_result.source},
            )
            yield emit_stage_event(
                stage_id=current_stage_id,
                stage_status="blocked",
                content="StageGraph v1-lite: planning failed; execution stopped.",
                metadata={"plan_source": plan_result.source},
            )
            yield emit_event(
                type="error",
                agent="planner",
                content="Planner could not generate a real LLM plan. This turn has stopped.",
                metadata={
                    "plan_source": plan_result.source,
                    "reason": plan_result.reasoning,
                    "stage_graph": stage_graph.snapshot(),
                },
                is_final=True,
            )
            finalize_llm_trace()
            return

        planning_snapshot = _build_planning_snapshot(plan_graph)
        append_stage_reasoning(current_stage_id, plan_graph.get("summary", ""))
        stage_graph.mark_completed(
            current_stage_id,
            note=plan_graph.get("title", "Plan generation completed."),
            metadata={
                "plan_graph_title": plan_graph.get("title", ""),
                "planning_snapshot": planning_snapshot,
            },
        )
        yield emit_stage_event(
            stage_id=current_stage_id,
            stage_status="completed",
            content="StageGraph v1-lite: planning completed.",
            metadata={
                "plan_graph_title": plan_graph.get("title", ""),
                "planning_snapshot": planning_snapshot,
                "stage_payload": planning_snapshot,
            },
        )

        yield emit_event(
            type="plan",
            agent="planner",
            content=f"Execution plan generated: {plan_graph.get('title', 'Execution plan')}",
            metadata=build_plan_metadata(plan_graph),
        )

        execution_results: dict[str, ExecutionResult] = {}
        replan_count = 0
        last_plan_sig = plan_graph_signature(plan_graph)

        async def emit_plan_update_if_changed() -> AsyncGenerator[AgentEvent, None]:
            nonlocal last_plan_sig
            current_sig = plan_graph_signature(plan_graph)
            if current_sig != last_plan_sig:
                last_plan_sig = current_sig
                yield emit_event(
                    type="plan_update",
                    agent="orchestrator",
                    content="Plan status updated.",
                    metadata=build_plan_metadata(plan_graph),
                )

        async def execute_nodes(nodes: list[dict[str, Any]]) -> AsyncGenerator[AgentEvent, None]:
            for node in nodes:
                if step >= MAX_TOTAL_STEPS:
                    break

                node_id = node["id"]
                if node.get("status") == "completed" or node_id in execution_results:
                    continue

                node["status"] = "in_progress"
                plan_graph["active_node_ids"] = [node_id]
                async for event in emit_plan_update_if_changed():
                    yield event

                yield emit_event(
                    type="agent_start",
                    agent="executor",
                    content=f"Executor is running: {node.get('title', '')}",
                    metadata={"node_id": node_id, "node_title": node.get("title", "")},
                )

                exec_result = await self.executor.execute_node(
                    node,
                    execution_results,
                    plan_graph,
                    user_query,
                    runtime_context,
                    understanding_result=understanding_result,
                )
                for trace_event in emit_new_llm_trace_events():
                    yield trace_event
                execution_results[node_id] = exec_result

                if exec_result.thinking:
                    append_stage_reasoning(current_stage_id, exec_result.thinking)
                    yield emit_event(
                        type="thinking",
                        agent="executor",
                        content=exec_result.thinking,
                        metadata={"node_id": node_id},
                    )

                if exec_result.tool_name:
                    action_meta = self.executor.build_action_metadata(exec_result, plan_graph)
                    action_meta["node_id"] = node_id
                    yield emit_event(
                        type="action",
                        agent="executor",
                        content=action_meta.get("tool_input_summary", f"Invoke {exec_result.tool_name}"),
                        metadata=action_meta,
                    )

                    observation_meta = self.executor.build_observation_metadata(exec_result, plan_graph)
                    observation_meta["node_id"] = node_id
                    observation_content = observation_meta.get("result_summary", "Execution completed.")
                    if exec_result.error:
                        observation_content = f"Execution error: {exec_result.error}"
                    yield emit_event(
                        type="observation",
                        agent="executor",
                        content=observation_content,
                        metadata=observation_meta,
                    )

                node["status"] = "completed"
                plan_graph["active_node_ids"] = []
                async for event in emit_plan_update_if_changed():
                    yield event

        while replan_count <= MAX_REPLAN_ATTEMPTS and step < MAX_TOTAL_STEPS:
            metric_nodes, detail_nodes = _partition_execution_nodes(plan_graph, execution_results)

            current_stage_id = "metric_execution"
            stage_graph.mark_in_progress(
                current_stage_id,
                note="Executing metric query and analysis nodes.",
                metadata={"node_count": len(metric_nodes)},
            )
            yield emit_stage_event(
                stage_id=current_stage_id,
                stage_status="in_progress",
                content="StageGraph v1-lite: entering metric execution.",
                metadata={"node_count": len(metric_nodes)},
            )

            async for event in execute_nodes(metric_nodes):
                yield event

            metric_note = "Metric execution completed." if metric_nodes else "No metric execution nodes in this pass."
            append_stage_reasoning(current_stage_id, metric_note)
            stage_graph.mark_completed(
                current_stage_id,
                note=metric_note,
                metadata={"completed_node_count": len(metric_nodes)},
            )
            yield emit_stage_event(
                stage_id=current_stage_id,
                stage_status="completed",
                content="StageGraph v1-lite: metric execution completed.",
                metadata={"completed_node_count": len(metric_nodes)},
            )

            current_stage_id = "detail_execution"
            stage_graph.mark_in_progress(
                current_stage_id,
                note=(
                    "Executing detail drill-down nodes."
                    if detail_nodes
                    else "No detail drill-down nodes in this pass; stage closes immediately."
                ),
                metadata={"node_count": len(detail_nodes)},
            )
            yield emit_stage_event(
                stage_id=current_stage_id,
                stage_status="in_progress",
                content="StageGraph v1-lite: entering detail drill-down execution.",
                metadata={"node_count": len(detail_nodes)},
            )

            async for event in execute_nodes(detail_nodes):
                yield event

            detail_note = "Detail drill-down completed." if detail_nodes else "No detail drill-down required in this pass."
            append_stage_reasoning(current_stage_id, detail_note)
            stage_graph.mark_completed(
                current_stage_id,
                note=detail_note,
                metadata={"completed_node_count": len(detail_nodes)},
            )
            yield emit_stage_event(
                stage_id=current_stage_id,
                stage_status="completed",
                content="StageGraph v1-lite: detail drill-down completed.",
                metadata={"completed_node_count": len(detail_nodes)},
            )

            current_stage_id = "evidence_verification"
            stage_graph.mark_in_progress(current_stage_id, note="Validating execution outputs and evidence completeness.")
            yield emit_stage_event(
                stage_id=current_stage_id,
                stage_status="in_progress",
                content="StageGraph v1-lite: entering evidence verification.",
            )

            verification_note, verification_metadata = _build_evidence_verification(plan_graph, execution_results)
            append_stage_reasoning(current_stage_id, verification_note)
            stage_graph.mark_completed(
                current_stage_id,
                note=verification_note,
                metadata=verification_metadata,
            )
            yield emit_stage_event(
                stage_id=current_stage_id,
                stage_status="completed",
                content="StageGraph v1-lite: evidence verification completed.",
                metadata=verification_metadata,
            )

            current_stage_id = "review"
            stage_graph.mark_in_progress(current_stage_id, note="Reviewer is validating key execution outputs.")
            yield emit_stage_event(
                stage_id=current_stage_id,
                stage_status="in_progress",
                content="StageGraph v1-lite: entering review stage.",
            )

            reviewable_nodes = [
                node for node in plan_graph.get("nodes", [])
                if node.get("id") in execution_results
                and node.get("kind") in {"query", "analysis"}
                and execution_results[node["id"]].tool_name
            ]
            reject_review: tuple[dict[str, Any], Any] | None = None

            for node in reviewable_nodes:
                node_id = node["id"]
                yield emit_event(
                    type="agent_start",
                    agent="reviewer",
                    content=f"Reviewer is evaluating: {node.get('title', '')}",
                    metadata={"node_id": node_id},
                )

                review = await self.reviewer.review(node, execution_results[node_id], user_query)
                for trace_event in emit_new_llm_trace_events():
                    yield trace_event
                review_content = review.summary or ("Review approved." if review.verdict == "approve" else "Review rejected.")
                append_stage_reasoning(current_stage_id, review_content)
                yield emit_event(
                    type="review",
                    agent="reviewer",
                    content=review_content,
                    metadata={
                        "node_id": node_id,
                        "verdict": review.verdict,
                        "review_points": review.review_points,
                        "issues": review.issues,
                        "suggestions": review.suggestions,
                    },
                )
                if review.verdict == "reject":
                    reject_review = (node, review)
                    break

            if reject_review is None:
                review_note = "All reviewable nodes passed review."
                if not reviewable_nodes:
                    review_note = "No reviewable query/analysis nodes in this pass."
                append_stage_reasoning(current_stage_id, review_note)
                stage_graph.mark_completed(
                    current_stage_id,
                    note=review_note,
                    metadata={"reviewed_node_count": len(reviewable_nodes)},
                )
                yield emit_stage_event(
                    stage_id=current_stage_id,
                    stage_status="completed",
                    content="StageGraph v1-lite: review completed.",
                    metadata={"reviewed_node_count": len(reviewable_nodes)},
                )
                break

            rejected_node, rejected_review = reject_review
            rejected_node_id = rejected_node["id"]

            if replan_count >= MAX_REPLAN_ATTEMPTS:
                final_review_note = rejected_review.summary or "Review rejected and max replan attempts reached."
                append_stage_reasoning(current_stage_id, final_review_note)
                stage_graph.mark_blocked(
                    current_stage_id,
                    note=final_review_note,
                    metadata={"node_id": rejected_node_id, "issues": rejected_review.issues},
                )
                yield emit_stage_event(
                    stage_id=current_stage_id,
                    stage_status="blocked",
                    content="StageGraph v1-lite: review failed and max replan attempts reached.",
                    metadata={"node_id": rejected_node_id, "issues": rejected_review.issues},
                )
                yield emit_event(
                    type="error",
                    agent="reviewer",
                    content=rejected_review.summary or "Review failed. Execution stopped.",
                    metadata={"stage_graph": stage_graph.snapshot(), "issues": rejected_review.issues},
                    is_final=True,
                )
                finalize_llm_trace()
                return

            blocked_review_note = rejected_review.summary or "Review rejected. Triggering replan."
            append_stage_reasoning(current_stage_id, blocked_review_note)
            stage_graph.mark_blocked(
                current_stage_id,
                note=blocked_review_note,
                metadata={"node_id": rejected_node_id, "issues": rejected_review.issues},
            )
            yield emit_stage_event(
                stage_id=current_stage_id,
                stage_status="blocked",
                content="StageGraph v1-lite: review rejected, preparing replan.",
                metadata={"node_id": rejected_node_id, "issues": rejected_review.issues},
            )
            yield emit_event(
                type="replan_trigger",
                agent="reviewer",
                content=f"Review rejected; replan triggered: {rejected_review.summary or ''}",
                metadata={
                    "reason": rejected_review.summary,
                    "issues": rejected_review.issues,
                    "original_node_id": rejected_node_id,
                },
            )

            execution_results.pop(rejected_node_id, None)
            for node in plan_graph.get("nodes", []):
                if node.get("id") == rejected_node_id:
                    node["status"] = "pending"

            current_stage_id = "planning"
            stage_graph.mark_in_progress(current_stage_id, note="Replanning based on reviewer feedback.")
            yield emit_stage_event(
                stage_id=current_stage_id,
                stage_status="in_progress",
                content="StageGraph v1-lite: replanning from reviewer feedback.",
                metadata={"node_id": rejected_node_id, "issues": rejected_review.issues},
            )
            yield emit_event(
                type="agent_start",
                agent="planner",
                content="Planner is revising the plan from review feedback.",
            )

            replan_result = await self.planner.replan(
                user_query,
                plan_graph,
                rejected_review.to_dict(),
                {"completed_nodes": list(execution_results.keys())},
                runtime_context,
                understanding_result=understanding_result,
            )
            for trace_event in emit_new_llm_trace_events():
                yield trace_event
            plan_graph = replan_result.graph
            replan_count += 1

            if replan_result.reasoning:
                append_stage_reasoning(current_stage_id, replan_result.reasoning)
                yield emit_event(
                    type="thinking",
                    agent="planner",
                    content=replan_result.reasoning,
                )

            if replan_result.source != "llm" or plan_graph.get("source") != "llm":
                replanning_failure_note = "Planner failed to produce a real LLM replan."
                append_stage_reasoning(current_stage_id, replanning_failure_note)
                stage_graph.mark_blocked(
                    current_stage_id,
                    note=replanning_failure_note,
                    metadata={"plan_source": replan_result.source, "node_id": rejected_node_id},
                )
                yield emit_stage_event(
                    stage_id=current_stage_id,
                    stage_status="blocked",
                    content="StageGraph v1-lite: replanning failed; execution stopped.",
                    metadata={"plan_source": replan_result.source, "node_id": rejected_node_id},
                )
                yield emit_event(
                    type="error",
                    agent="planner",
                    content="Planner failed to generate a real LLM replan. This turn was stopped.",
                    metadata={"stage_graph": stage_graph.snapshot()},
                    is_final=True,
                )
                finalize_llm_trace()
                return

            planning_snapshot = _build_planning_snapshot(plan_graph)
            replan_note = _clean_text(plan_graph.get("change_reason")) or "Replanning completed."
            append_stage_reasoning(current_stage_id, replan_note)
            stage_graph.mark_completed(
                current_stage_id,
                note=replan_note,
                metadata={
                    "plan_graph_title": plan_graph.get("title", ""),
                    "node_id": rejected_node_id,
                    "planning_snapshot": planning_snapshot,
                },
            )
            yield emit_stage_event(
                stage_id=current_stage_id,
                stage_status="completed",
                content="StageGraph v1-lite: replanning completed.",
                metadata={
                    "plan_graph_title": plan_graph.get("title", ""),
                    "node_id": rejected_node_id,
                    "planning_snapshot": planning_snapshot,
                    "stage_payload": planning_snapshot,
                },
            )
            yield emit_event(
                type="plan_update",
                agent="planner",
                content=f"Plan revised: {plan_graph.get('change_reason', '')}",
                metadata=build_plan_metadata(plan_graph),
            )
            last_plan_sig = plan_graph_signature(plan_graph)

        if step >= MAX_TOTAL_STEPS:
            yield emit_event(
                type="error",
                agent="orchestrator",
                content="Step limit exceeded; this turn has stopped.",
                metadata={"stage_graph": stage_graph.snapshot()},
                is_final=True,
            )
            finalize_llm_trace()
            return

        current_stage_id = "report_generation"
        stage_graph.mark_in_progress(current_stage_id, note="Synthesizing final answer from execution evidence.")
        yield emit_stage_event(
            stage_id=current_stage_id,
            stage_status="in_progress",
            content="StageGraph v1-lite: entering report generation.",
        )
        yield emit_event(
            type="agent_start",
            agent="reviewer",
            content="Reviewer is synthesizing the final answer.",
        )

        synthesis = await self.reviewer.synthesize(user_query, execution_results, plan_graph)
        for trace_event in emit_new_llm_trace_events():
            yield trace_event

        if not synthesis.success:
            report_failure_note = synthesis.failure_reason or "Report generation failed."
            append_stage_reasoning(current_stage_id, report_failure_note)
            stage_graph.mark_blocked(
                current_stage_id,
                note=report_failure_note,
                metadata={"evidence_count": len(synthesis.evidence), "failure_reason": synthesis.failure_reason},
            )
            yield emit_stage_event(
                stage_id=current_stage_id,
                stage_status="blocked",
                content="StageGraph v1-lite: report generation failed.",
                metadata={"evidence_count": len(synthesis.evidence), "failure_reason": synthesis.failure_reason},
            )
            yield emit_event(
                type="error",
                agent="reviewer",
                content=report_failure_note,
                metadata={"stage_graph": stage_graph.snapshot(), "evidence": synthesis.evidence},
                is_final=True,
            )
            finalize_llm_trace()
            return

        for node in plan_graph.get("nodes", []):
            if node.get("status") != "skipped":
                node["status"] = "completed"
        plan_graph["active_node_ids"] = []

        yield emit_event(
            type="plan_update",
            agent="orchestrator",
            content="All plan nodes completed.",
            metadata=build_plan_metadata(plan_graph),
        )

        report_note = f"Final report generated with {len(synthesis.evidence)} evidence items."
        append_stage_reasoning(current_stage_id, report_note)
        stage_graph.mark_completed(
            current_stage_id,
            note=report_note,
            metadata={"evidence_count": len(synthesis.evidence)},
        )
        yield emit_stage_event(
            stage_id=current_stage_id,
            stage_status="completed",
            content="StageGraph v1-lite: report generation completed.",
            metadata={"evidence_count": len(synthesis.evidence)},
        )

        yield emit_event(
            type="answer",
            agent="reviewer",
            content=synthesis.answer,
            metadata={"evidence": synthesis.evidence},
            is_final=True,
        )
        self.conversation_history.append({"role": "user", "content": user_query})
        self.conversation_history.append({"role": "assistant", "content": synthesis.answer})
        if len(self.conversation_history) > 20:
            self.conversation_history = self.conversation_history[-20:]
        finalize_llm_trace()


