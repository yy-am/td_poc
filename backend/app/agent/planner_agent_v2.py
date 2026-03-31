"""Planner Agent with runtime grounding and plan validation."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from app.agent.plan_presentation import (
    build_fallback_plan_graph,
    normalize_plan_graph,
    normalize_semantic_binding,
)
from app.agent.planner import append_planner_debug_log, parse_plan_json, trim_conversation_history
from app.agent.prompts.planner_prompt_v3 import PLANNER_SYSTEM_PROMPT, REPLAN_SYSTEM_PROMPT
from app.agent.runtime_context import build_runtime_context, validate_plan_graph


class PlanResult:
    """Container for planner output."""

    __slots__ = ("graph", "reasoning", "source")

    def __init__(self, graph: dict[str, Any], reasoning: str, source: str):
        self.graph = graph
        self.reasoning = reasoning
        self.source = source


class PlannerAgent:
    """Generates and revises DAG execution plans."""

    def __init__(self, llm: Any):
        self.llm = llm

    @staticmethod
    def _truncate_text(value: Any, limit: int) -> str:
        text = str(value or "").strip()
        if len(text) <= limit:
            return text
        return text[: limit - 1].rstrip() + "…"

    @staticmethod
    def _merge_unique(*groups: list[Any]) -> list[str]:
        merged: list[str] = []
        for group in groups:
            for item in group or []:
                text = str(item or "").strip()
                if text and text not in merged:
                    merged.append(text)
        return merged

    def _normalize_fallback_policy(self, value: Any) -> str:
        policy = str(value or "").strip().lower()
        if policy in {"semantic_only", "none"}:
            return "semantic_only"
        if policy in {"fallback_to_atomic_fact", "atomic_then_sql", "fallback_to_sql"}:
            return "atomic_then_sql"
        return "atomic_then_sql"

    @staticmethod
    def _normalize_match_text(value: Any) -> str:
        text = str(value or "").strip().lower()
        if not text:
            return ""
        return "".join(
            char
            for char in text
            if char.isalnum() or char == "_" or "\u4e00" <= char <= "\u9fff"
        )

    def _build_query_fragments(self, user_query: str) -> list[str]:
        normalized_query = self._normalize_match_text(user_query)
        if not normalized_query:
            return []

        raw_fragments = re.split(
            r"[，。；;、\s]+|(?:并且|以及|然后|同时|和|与)",
            user_query or "",
        )
        fragments: list[str] = [normalized_query]
        for item in raw_fragments:
            normalized = self._normalize_match_text(item)
            if len(normalized) >= 2 and normalized not in fragments:
                fragments.append(normalized)
        return fragments

    @staticmethod
    def _wants_explicit_drilldown(user_query: str) -> bool:
        text = str(user_query or "").strip()
        if not text:
            return False
        return any(keyword in text for keyword in ("下钻", "明细字段", "返回明细字段"))

    @staticmethod
    def _bigram_overlap_score(left: str, right: str) -> int:
        if len(left) < 2 or len(right) < 2:
            return 0
        left_bigrams = {left[idx : idx + 2] for idx in range(len(left) - 1)}
        right_bigrams = {right[idx : idx + 2] for idx in range(len(right) - 1)}
        return len(left_bigrams & right_bigrams)

    def _term_aliases(self, term: Any) -> list[str]:
        aliases: list[str] = []
        if isinstance(term, dict):
            values = [term.get("name"), term.get("label"), term.get("display_name"), term.get("column")]
        else:
            values = [term]
        for value in values:
            normalized = self._normalize_match_text(value)
            if normalized and normalized not in aliases:
                aliases.append(normalized)
        return aliases

    def _score_term(self, term: Any, fragments: list[str]) -> int:
        aliases = self._term_aliases(term)
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
                score += min(self._bigram_overlap_score(fragment, alias) * 3, 9)
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

    def _select_terms_for_seed(
        self,
        terms: list[Any],
        *,
        requested_terms: list[str],
        user_query: str,
        limit: int,
    ) -> list[str]:
        if not terms:
            return []

        requested_lookup = {
            self._normalize_match_text(item)
            for item in requested_terms
            if self._normalize_match_text(item)
        }
        if requested_lookup:
            selected: list[str] = []
            for item in terms:
                aliases = self._term_aliases(item)
                if not aliases:
                    continue
                if any(alias in requested_lookup for alias in aliases):
                    name = str(item.get("name") or item.get("column") or "").strip() if isinstance(item, dict) else str(item or "").strip()
                    if name and name not in selected:
                        selected.append(name)
            if selected:
                return selected[:limit]

        fragments = self._build_query_fragments(user_query)
        if not fragments:
            return []

        scored: list[tuple[int, int, str]] = []
        for index, item in enumerate(terms):
            score = self._score_term(item, fragments)
            if score <= 0:
                continue
            name = str(item.get("name") or item.get("column") or "").strip() if isinstance(item, dict) else str(item or "").strip()
            if not name:
                continue
            scored.append((score, index, name))

        scored.sort(key=lambda record: (-record[0], record[1]))
        selected_names: list[str] = []
        for _, _, name in scored:
            if name not in selected_names:
                selected_names.append(name)

        def append_first(predicate: Any) -> None:
            if len(selected_names) >= limit:
                return
            for item in terms:
                name = str(item.get("name") or item.get("column") or "").strip() if isinstance(item, dict) else str(item or "").strip()
                if not name or name in selected_names:
                    continue
                aliases = self._term_aliases(item)
                if predicate(aliases):
                    selected_names.append(name)
                    return

        if any("差异" in fragment for fragment in fragments):
            append_first(lambda aliases: any("差异" in alias for alias in aliases))
        if any("税基" in fragment for fragment in fragments):
            append_first(lambda aliases: any("税基" in alias for alias in aliases))
        if any("账面" in fragment for fragment in fragments) and any("收入" in fragment for fragment in fragments):
            append_first(lambda aliases: any("账面" in alias and "收入" in alias for alias in aliases))
        if any("折扣" in fragment for fragment in fragments) and any("单" in fragment for fragment in fragments):
            append_first(lambda aliases: any("折扣" in alias and "单" in alias and "号" in alias for alias in aliases))

        return selected_names[:limit]

    def _infer_binding_time_context(
        self,
        *,
        runtime_context: dict[str, Any],
        grain: str,
        time_field: str,
    ) -> dict[str, Any]:
        period_hints = runtime_context.get("period_hints") or {}
        year = period_hints.get("year")
        quarter = period_hints.get("quarter")
        periods = self._merge_unique(period_hints.get("periods") or [])

        range_value = ""
        if year and quarter and time_field and not time_field.endswith("year"):
            range_value = f"{year}Q{quarter}"
        elif len(periods) == 1:
            range_value = periods[0]
        elif len(periods) > 1:
            range_value = f"{periods[0]}..{periods[-1]}"
        elif year:
            range_value = str(year)

        if not grain and not range_value:
            return {}

        payload: dict[str, Any] = {}
        if grain:
            payload["grain"] = grain
        if range_value:
            payload["range"] = range_value
        return payload

    def _infer_binding_seed(self, runtime_context: dict[str, Any], user_query: str = "") -> dict[str, Any]:
        understanding_result = runtime_context.get("understanding_result") or {}
        semantic_scope = understanding_result.get("semantic_scope") or {}
        relevant_models = runtime_context.get("relevant_models") or []
        model_by_name = {
            str(item.get("name") or "").strip(): item
            for item in relevant_models
            if str(item.get("name") or "").strip()
        }

        composite_models = self._merge_unique(semantic_scope.get("composite_models") or [])
        atomic_models = self._merge_unique(semantic_scope.get("atomic_models") or [])
        entity_models = self._merge_unique(semantic_scope.get("entity_models") or [])
        semantic_ready = [
            str(item.get("name") or "").strip()
            for item in relevant_models
            if item.get("has_yaml_definition") and str(item.get("name") or "").strip()
        ]

        entry_model = ""
        for candidates in (composite_models, atomic_models, semantic_ready, entity_models):
            if candidates:
                entry_model = candidates[0]
                break

        supporting_models = self._merge_unique(
            [name for name in composite_models if name != entry_model],
            [name for name in atomic_models if name != entry_model],
            [name for name in entity_models if name != entry_model],
            [name for name in semantic_ready if name != entry_model],
        )[:6]

        entry_metadata = model_by_name.get(entry_model, {})
        entry_time = entry_metadata.get("time") or {}
        time_field = str(entry_time.get("field") or "").strip() or "period"
        semantic_kind = str(entry_metadata.get("semantic_kind") or "").strip()
        preferred_lane = str((entry_metadata.get("query_hints") or {}).get("preferred_lane") or "").strip().lower()
        recommended_tool = str(entry_metadata.get("recommended_tool") or "").strip()
        if not recommended_tool:
            if semantic_kind == "composite_analysis" and preferred_lane == "metric":
                recommended_tool = "mql_query"
            elif entry_metadata.get("has_yaml_definition"):
                recommended_tool = "semantic_query"

        requested_dimensions = self._merge_unique(understanding_result.get("dimensions") or [])
        requested_metrics = self._merge_unique(understanding_result.get("metrics") or [])
        dimensions = self._select_terms_for_seed(
            entry_metadata.get("dimension_terms") or entry_metadata.get("dimensions") or [],
            requested_terms=requested_dimensions,
            user_query=user_query,
            limit=8,
        )
        metrics = self._select_terms_for_seed(
            entry_metadata.get("metric_terms") or entry_metadata.get("metrics") or [],
            requested_terms=requested_metrics,
            user_query=user_query,
            limit=8,
        )

        entities = understanding_result.get("entities") or {}
        enterprise_names = self._merge_unique(
            entities.get("enterprise_names") or [],
            [
                item.get("enterprise_name")
                for item in (runtime_context.get("enterprise_candidates") or [])
                if item.get("enterprise_name")
            ],
        )[:5]
        taxpayer_ids = self._merge_unique(
            entities.get("taxpayer_ids") or [],
            [
                item.get("taxpayer_id")
                for item in (runtime_context.get("enterprise_candidates") or [])
                if item.get("taxpayer_id")
            ],
        )[:5]

        entity_filters: dict[str, list[Any]] = {}
        if enterprise_names:
            entity_filters["enterprise_name"] = enterprise_names

        resolved_filters: dict[str, list[Any]] = {}
        if taxpayer_ids and not entity_filters:
            resolved_filters["taxpayer_id"] = taxpayer_ids

        period_hints = runtime_context.get("period_hints") or {}
        periods = self._merge_unique(period_hints.get("periods") or [], entities.get("periods") or [])[:12]
        filters: list[dict[str, Any]] = []
        if periods:
            filters.append({"field": time_field, "op": "in", "value": periods})

        grain = ""
        if periods:
            grain = "month"
        elif period_hints.get("quarter"):
            grain = "quarter"
        elif period_hints.get("year"):
            grain = "year"
        elif str(entry_time.get("grain") or "").strip():
            grain = str(entry_time.get("grain") or "").strip()

        query_language = "tda_mql" if recommended_tool == "mql_query" else ""
        time_context = self._infer_binding_time_context(
            runtime_context=runtime_context,
            grain=grain,
            time_field=time_field,
        )
        drilldown: dict[str, Any] = {}
        supports_drilldown = bool((entry_metadata.get("query_hints") or {}).get("supports_drilldown"))
        detail_fields = self._select_terms_for_seed(
            entry_metadata.get("detail_fields") or [],
            requested_terms=[],
            user_query=user_query,
            limit=8,
        )
        if self._wants_explicit_drilldown(user_query) and (supports_drilldown or detail_fields):
            drilldown = {
                "enabled": True,
                "target": entry_model,
                "detail_fields": detail_fields,
                "limit": 200,
            }

        return {
            "entry_model": entry_model,
            "supporting_models": supporting_models,
            "dimensions": dimensions,
            "metrics": metrics,
            "entity_filters": entity_filters,
            "resolved_filters": resolved_filters,
            "grain": grain,
            "fallback_policy": self._normalize_fallback_policy(entry_metadata.get("fallback_policy")),
            "filters": filters,
            "recommended_tool": recommended_tool,
            "query_language": query_language,
            "time_context": time_context,
            "drilldown": drilldown,
        }

    def _compact_understanding_result(self, understanding_result: dict[str, Any]) -> dict[str, Any]:
        entities = understanding_result.get("entities") or {}
        semantic_scope = understanding_result.get("semantic_scope") or {}
        return {
            "query_mode": str(understanding_result.get("query_mode") or "").strip(),
            "intent_summary": self._truncate_text(understanding_result.get("intent_summary"), 160),
            "business_goal": self._truncate_text(understanding_result.get("business_goal"), 160),
            "entities": {
                "enterprise_names": self._merge_unique(entities.get("enterprise_names") or [])[:5],
                "taxpayer_ids": self._merge_unique(entities.get("taxpayer_ids") or [])[:5],
                "tax_types": self._merge_unique(entities.get("tax_types") or [])[:5],
                "periods": self._merge_unique(entities.get("periods") or [])[:8],
            },
            "semantic_scope": {
                "entity_models": self._merge_unique(semantic_scope.get("entity_models") or [])[:6],
                "atomic_models": self._merge_unique(semantic_scope.get("atomic_models") or [])[:6],
                "composite_models": self._merge_unique(semantic_scope.get("composite_models") or [])[:6],
            },
            "dimensions": self._merge_unique(understanding_result.get("dimensions") or [])[:8],
            "metrics": self._merge_unique(understanding_result.get("metrics") or [])[:8],
            "required_evidence": self._merge_unique(understanding_result.get("required_evidence") or [])[:6],
            "resolution_requirements": self._merge_unique(understanding_result.get("resolution_requirements") or [])[:6],
            "candidate_models": self._merge_unique(understanding_result.get("candidate_models") or [])[:6],
            "ambiguities": self._merge_unique(understanding_result.get("ambiguities") or [])[:6],
            "confidence": str(understanding_result.get("confidence") or "").strip(),
        }

    def _compact_runtime_context_for_prompt(self, runtime_context: dict[str, Any]) -> dict[str, Any]:
        relevant_models: list[dict[str, Any]] = []
        for item in (runtime_context.get("relevant_models") or [])[:6]:
            time_meta = item.get("time") or {}
            query_hints = item.get("query_hints") or {}
            relevant_models.append(
                {
                    "name": str(item.get("name") or "").strip(),
                    "label": self._truncate_text(item.get("label"), 40),
                    "description": self._truncate_text(item.get("description"), 120),
                    "semantic_kind": str(item.get("semantic_kind") or "").strip(),
                    "semantic_domain": str(item.get("semantic_domain") or "").strip(),
                    "semantic_grain": str(item.get("semantic_grain") or "").strip(),
                    "recommended_tool": str(item.get("recommended_tool") or "").strip(),
                    "fallback_policy": str(item.get("fallback_policy") or "").strip(),
                    "supports_entity_resolution": bool(item.get("supports_entity_resolution")),
                    "business_terms": self._merge_unique(item.get("business_terms") or [])[:6],
                    "intent_aliases": self._merge_unique(item.get("intent_aliases") or [])[:6],
                    "analysis_patterns": self._merge_unique(item.get("analysis_patterns") or [])[:5],
                    "dimensions": self._merge_unique(item.get("dimensions") or [])[:8],
                    "metrics": self._merge_unique(item.get("metrics") or [])[:8],
                    "detail_fields": self._merge_unique(
                        [
                            (field.get("name") if isinstance(field, dict) else field)
                            for field in (item.get("detail_fields") or [])
                        ]
                    )[:8],
                    "time": {
                        "field": str(time_meta.get("field") or "").strip(),
                        "grain": str(time_meta.get("grain") or "").strip(),
                        "available_grains": self._merge_unique(time_meta.get("available_grains") or [])[:4],
                    },
                    "query_hints": {
                        "preferred_lane": str(query_hints.get("preferred_lane") or "").strip(),
                        "supports_drilldown": bool(query_hints.get("supports_drilldown")),
                        "recommended_patterns": self._merge_unique(query_hints.get("recommended_patterns") or [])[:4],
                    },
                }
            )

        table_schemas: list[dict[str, Any]] = []
        for item in (runtime_context.get("relevant_table_schemas") or [])[:4]:
            columns = []
            for column in (item.get("columns") or [])[:10]:
                columns.append(
                    {
                        "name": str(column.get("name") or "").strip(),
                        "type": str(column.get("type") or "").strip(),
                    }
                )
            table_schemas.append(
                {
                    "table_name": str(item.get("table_name") or "").strip(),
                    "columns": columns,
                    "has_taxpayer_id": bool(item.get("has_taxpayer_id")),
                    "has_enterprise_name": bool(item.get("has_enterprise_name")),
                    "has_period": bool(item.get("has_period")),
                }
            )

        enterprise_candidates: list[dict[str, str]] = []
        for item in (runtime_context.get("enterprise_candidates") or [])[:5]:
            enterprise_candidates.append(
                {
                    "enterprise_name": str(item.get("enterprise_name") or "").strip(),
                    "taxpayer_id": str(item.get("taxpayer_id") or "").strip(),
                }
            )

        return {
            "query_mode": str(runtime_context.get("query_mode") or "").strip(),
            "classification_confidence": str(runtime_context.get("classification_confidence") or "").strip(),
            "matched_keywords": self._merge_unique(runtime_context.get("matched_keywords") or [])[:8],
            "all_query_keywords": self._merge_unique(runtime_context.get("all_query_keywords") or [])[:12],
            "period_hints": dict(runtime_context.get("period_hints") or {}),
            "company_fragments": self._merge_unique(runtime_context.get("company_fragments") or [])[:5],
            "enterprise_candidates": enterprise_candidates,
            "relevant_models": relevant_models,
            "relevant_tables": self._merge_unique(runtime_context.get("relevant_tables") or [])[:6],
            "relevant_table_schemas": table_schemas,
            "execution_guidance": self._merge_unique(runtime_context.get("execution_guidance") or [])[:8],
        }

    def _build_prompt_payload(
        self,
        *,
        user_query: str,
        conversation_history: list[dict[str, Any]],
        runtime_context: dict[str, Any],
        understanding_result: dict[str, Any],
        extra_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "user_query": user_query,
            "conversation_history": trim_conversation_history(conversation_history),
            "understanding_result": self._compact_understanding_result(understanding_result),
            "runtime_context": self._compact_runtime_context_for_prompt(runtime_context),
            "planning_seed": self._infer_binding_seed(runtime_context, user_query),
        }
        if extra_payload:
            payload.update(extra_payload)
        return payload

    def _enrich_plan_graph_with_runtime_semantics(
        self,
        plan_graph: dict[str, Any],
        runtime_context: dict[str, Any],
        user_query: str = "",
    ) -> dict[str, Any]:
        if runtime_context.get("query_mode") == "metadata":
            return plan_graph

        binding_seed = self._infer_binding_seed(runtime_context, user_query)
        if not binding_seed.get("entry_model"):
            return plan_graph

        for node in plan_graph.get("nodes", []) or []:
            if node.get("kind") not in {"query", "analysis"}:
                continue

            binding = normalize_semantic_binding(node.get("semantic_binding"))
            tool_hints = [str(item) for item in (node.get("tool_hints") or []) if str(item or "").strip()]
            binding["entry_model"] = str(binding.get("entry_model") or "").strip() or binding_seed["entry_model"]
            binding["supporting_models"] = self._merge_unique(
                binding.get("supporting_models") or [],
                binding_seed.get("supporting_models") or [],
            )[:6]
            binding["dimensions"] = self._merge_unique(
                binding.get("dimensions") or [],
                binding_seed.get("dimensions") or [],
            )[:8]
            binding["metrics"] = self._merge_unique(
                binding.get("metrics") or [],
                binding_seed.get("metrics") or [],
            )[:8]

            if not (binding.get("entity_filters") or {}):
                binding["entity_filters"] = dict(binding_seed.get("entity_filters") or {})
            if not (binding.get("resolved_filters") or {}):
                binding["resolved_filters"] = dict(binding_seed.get("resolved_filters") or {})
            if not str(binding.get("grain") or "").strip():
                binding["grain"] = binding_seed.get("grain") or ""
            if not str(binding.get("fallback_policy") or "").strip():
                binding["fallback_policy"] = binding_seed.get("fallback_policy") or "atomic_then_sql"
            if not (binding.get("filters") or []):
                binding["filters"] = list(binding_seed.get("filters") or [])
            if not str(binding.get("query_language") or "").strip():
                binding["query_language"] = binding_seed.get("query_language") or ""
            if not (binding.get("time_context") or {}):
                binding["time_context"] = dict(binding_seed.get("time_context") or {})
            if not (binding.get("drilldown") or {}) and (binding_seed.get("drilldown") or {}):
                binding["drilldown"] = dict(binding_seed.get("drilldown") or {})
                analysis_mode = binding.get("analysis_mode") if isinstance(binding.get("analysis_mode"), dict) else {}
                if not analysis_mode or str(analysis_mode.get("kind") or "").strip() in {"", "analysis"}:
                    binding["analysis_mode"] = {"kind": "drilldown", "label": "明细下钻"}

            use_mql = (
                str(binding.get("query_language") or "").strip().lower() == "tda_mql"
                or "mql_query" in tool_hints
                or binding_seed.get("recommended_tool") == "mql_query"
            )
            if use_mql:
                binding["query_language"] = "tda_mql"
                if not (binding.get("time_context") or {}):
                    binding["time_context"] = dict(binding_seed.get("time_context") or {})
                if not str(binding.get("fallback_policy") or "").strip():
                    binding["fallback_policy"] = "semantic_only"
            elif str(binding.get("query_language") or "").strip().lower() != "tda_mql":
                binding["query_language"] = ""

            binding = normalize_semantic_binding(binding)
            node["semantic_binding"] = binding
            if use_mql:
                node["tool_hints"] = ["mql_query", *[item for item in tool_hints if item not in {"mql_query", "semantic_query", "sql_executor"}]][:3]
            elif binding.get("entry_model") and "semantic_query" not in tool_hints:
                node["tool_hints"] = ["semantic_query", *tool_hints][:3]

        return plan_graph

    async def plan(
        self,
        user_query: str,
        conversation_history: list[dict[str, Any]],
        runtime_context: dict[str, Any] | None = None,
        understanding_result: dict[str, Any] | None = None,
    ) -> PlanResult:
        """Generate the initial execution plan."""
        runtime_context = runtime_context or await build_runtime_context(user_query)
        normalized_understanding = understanding_result or runtime_context.get("understanding_result") or {}
        payload = self._build_prompt_payload(
            user_query=user_query,
            conversation_history=conversation_history,
            runtime_context=runtime_context,
            understanding_result=normalized_understanding,
        )

        raw_content = ""
        try:
            reasoning, normalized, raw_content = await self._generate_valid_plan(
                user_query=user_query,
                runtime_context=runtime_context,
                system_prompt=PLANNER_SYSTEM_PROMPT,
                request_payload=payload,
                max_tokens=1200,
                timeout=45,
                change_reason_required=False,
            )
            return PlanResult(graph=normalized, reasoning=reasoning, source="llm")
        except Exception as exc:
            append_planner_debug_log(
                user_query=user_query,
                payload={"mode": "initial", "runtime_context": runtime_context},
                raw_content=raw_content,
                error=f"{type(exc).__name__}: {exc}",
            )
            fallback = build_fallback_plan_graph(user_query)
            return PlanResult(graph=fallback, reasoning="规划失败，使用保底路径。", source="fallback")

    async def replan(
        self,
        user_query: str,
        current_plan: dict[str, Any],
        review_feedback: dict[str, Any],
        execution_context: dict[str, Any] | None = None,
        runtime_context: dict[str, Any] | None = None,
        understanding_result: dict[str, Any] | None = None,
    ) -> PlanResult:
        """Revise the plan based on Reviewer feedback."""
        runtime_context = runtime_context or await build_runtime_context(user_query)
        normalized_understanding = understanding_result or runtime_context.get("understanding_result") or {}
        payload = self._build_prompt_payload(
            user_query=user_query,
            conversation_history=[],
            runtime_context=runtime_context,
            understanding_result=normalized_understanding,
            extra_payload={
                "current_plan": current_plan,
                "review_feedback": review_feedback,
                "execution_context": execution_context or {},
            },
        )

        raw_content = ""
        try:
            reasoning, normalized, raw_content = await self._generate_valid_plan(
                user_query=user_query,
                runtime_context=runtime_context,
                system_prompt=REPLAN_SYSTEM_PROMPT,
                request_payload=payload,
                max_tokens=1000,
                timeout=35,
                change_reason_required=True,
            )
            return PlanResult(graph=normalized, reasoning=reasoning, source="llm")
        except Exception as exc:
            append_planner_debug_log(
                user_query=user_query,
                payload={"mode": "replan", "runtime_context": runtime_context},
                raw_content=raw_content,
                error=f"{type(exc).__name__}: {exc}",
            )
            current_plan["change_reason"] = f"重规划失败（{exc}），沿用原计划。"
            return PlanResult(graph=current_plan, reasoning="重规划失败。", source="fallback")

    async def _generate_valid_plan(
        self,
        user_query: str,
        runtime_context: dict[str, Any],
        system_prompt: str,
        request_payload: dict[str, Any],
        max_tokens: int,
        timeout: int,
        change_reason_required: bool,
    ) -> tuple[str, dict[str, Any], str]:
        last_error: Exception | None = None
        validation_feedback: list[str] = []
        raw_content = ""

        for _attempt in range(2):
            payload = dict(request_payload)
            if validation_feedback:
                payload["validation_feedback"] = validation_feedback

            response = await asyncio.wait_for(
                self.llm.chat(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                    ],
                    trace={
                        "agent": "planner",
                        "operation": "replan_generate" if change_reason_required else "plan_generate",
                        "attempt": _attempt + 1,
                    },
                    stream=False,
                    temperature=0.0,
                    max_tokens=max_tokens,
                    response_format={"type": "json_object"},
                ),
                timeout=timeout,
            )
            raw_content = response.choices[0].message.content or ""
            parsed = parse_plan_json(raw_content)
            if not parsed:
                last_error = ValueError("planner returned empty JSON")
                validation_feedback = ["上一版输出不是有效 JSON，请只返回完整 JSON 对象。"]
                continue

            reasoning = str(parsed.get("reasoning", ""))
            plan_graph_raw = parsed.get("plan_graph", parsed)
            if "nodes" not in plan_graph_raw and "nodes" in parsed:
                plan_graph_raw = parsed

            normalized = normalize_plan_graph(plan_graph_raw, user_query=user_query)
            normalized = self._enrich_plan_graph_with_runtime_semantics(normalized, runtime_context, user_query)
            normalized["source"] = "llm"
            if change_reason_required and not normalized.get("change_reason"):
                normalized["change_reason"] = reasoning[:120]

            issues = validate_plan_graph(normalized, runtime_context)
            if not issues:
                return reasoning, normalized, raw_content

            validation_feedback = issues
            last_error = ValueError("; ".join(issues))

        raise last_error or ValueError("planner failed to generate a valid plan")
