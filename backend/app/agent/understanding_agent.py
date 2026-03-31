"""LLM-based business understanding layer for agent orchestration."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from app.agent.planner import parse_plan_json, trim_conversation_history
from app.agent.prompts.understanding_prompt_v1 import UNDERSTANDING_SYSTEM_PROMPT

ALLOWED_QUERY_MODES = {"metadata", "fact_query", "analysis", "reconciliation", "diagnosis"}
ALLOWED_CONFIDENCE = {"low", "medium", "high"}
SEMANTIC_SCOPE_KEYS = ("entity_models", "atomic_models", "composite_models")


class UnderstandingResult:
    """Normalized result produced by the understanding layer."""

    __slots__ = (
        "query_mode",
        "intent_summary",
        "business_goal",
        "entities",
        "semantic_scope",
        "dimensions",
        "metrics",
        "comparisons",
        "required_evidence",
        "resolution_requirements",
        "candidate_models",
        "ambiguities",
        "confidence",
        "used_fallback",
        "failure_type",
        "failure_message",
    )

    def __init__(
        self,
        query_mode: str = "fact_query",
        intent_summary: str = "",
        business_goal: str = "",
        entities: dict[str, Any] | None = None,
        semantic_scope: dict[str, list[str]] | None = None,
        dimensions: list[str] | None = None,
        metrics: list[str] | None = None,
        comparisons: list[dict[str, Any]] | None = None,
        required_evidence: list[str] | None = None,
        resolution_requirements: list[str] | None = None,
        candidate_models: list[str] | None = None,
        ambiguities: list[str] | None = None,
        confidence: str = "medium",
        used_fallback: bool = False,
        failure_type: str = "",
        failure_message: str = "",
    ):
        self.query_mode = query_mode if query_mode in ALLOWED_QUERY_MODES else "fact_query"
        self.intent_summary = intent_summary.strip()
        self.business_goal = business_goal.strip()
        self.entities = entities or {
            "enterprise_names": [],
            "taxpayer_ids": [],
            "tax_types": [],
            "periods": [],
        }
        self.semantic_scope = semantic_scope or {
            "entity_models": [],
            "atomic_models": [],
            "composite_models": [],
        }
        self.dimensions = dimensions or []
        self.metrics = metrics or []
        self.comparisons = comparisons or []
        self.required_evidence = required_evidence or []
        self.resolution_requirements = resolution_requirements or []
        self.candidate_models = candidate_models or []
        self.ambiguities = ambiguities or []
        self.confidence = confidence if confidence in ALLOWED_CONFIDENCE else "medium"
        self.used_fallback = bool(used_fallback)
        self.failure_type = failure_type.strip()
        self.failure_message = failure_message.strip()

    def to_dict(self) -> dict[str, Any]:
        return {
            "query_mode": self.query_mode,
            "intent_summary": self.intent_summary,
            "business_goal": self.business_goal,
            "entities": self.entities,
            "semantic_scope": self.semantic_scope,
            "dimensions": self.dimensions,
            "metrics": self.metrics,
            "comparisons": self.comparisons,
            "required_evidence": self.required_evidence,
            "resolution_requirements": self.resolution_requirements,
            "candidate_models": self.candidate_models,
            "ambiguities": self.ambiguities,
            "confidence": self.confidence,
            "used_fallback": self.used_fallback,
            "failure_type": self.failure_type,
            "failure_message": self.failure_message,
        }


class UnderstandingAgent:
    """Uses the LLM to convert user questions into structured business intent."""

    def __init__(self, llm: Any):
        self.llm = llm

    async def understand(
        self,
        user_query: str,
        conversation_history: list[dict[str, Any]],
        semantic_grounding: dict[str, Any],
    ) -> UnderstandingResult:
        payload = {
            "user_query": user_query,
            "conversation_history": trim_conversation_history(conversation_history),
            "semantic_grounding": self._compact_grounding(semantic_grounding),
        }

        try:
            response = await asyncio.wait_for(
                self.llm.chat(
                    messages=[
                        {"role": "system", "content": UNDERSTANDING_SYSTEM_PROMPT},
                        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                    ],
                    trace={"agent": "understanding", "operation": "intent_understanding"},
                    stream=False,
                    temperature=0.0,
                    max_tokens=900,
                    response_format={"type": "json_object"},
                ),
                timeout=30,
            )
        except asyncio.TimeoutError:
            return self._finalize_fallback_result(
                self._build_fallback_result(user_query, semantic_grounding),
                user_query=user_query,
                failure_type="llm_timeout",
                failure_message="意图识别调用超时，30 秒内未收到模型响应。",
            )
        except Exception as exc:
            return self._finalize_fallback_result(
                self._build_fallback_result(user_query, semantic_grounding),
                user_query=user_query,
                failure_type=self._classify_failure_type(exc),
                failure_message=self._build_failure_message(exc),
            )

        raw_content = response.choices[0].message.content or ""
        parsed = parse_plan_json(raw_content)
        if not parsed:
            return self._finalize_fallback_result(
                self._build_fallback_result(user_query, semantic_grounding),
                user_query=user_query,
                failure_type="response_parse_failed",
                failure_message="意图识别返回内容不可解析，未能提取合法 JSON 结果。",
            )

        try:
            return self._normalize_result(parsed, semantic_grounding)
        except Exception as exc:
            return self._finalize_fallback_result(
                self._build_fallback_result(user_query, semantic_grounding),
                user_query=user_query,
                failure_type="normalize_failed",
                failure_message=f"意图识别结果归一化失败：{type(exc).__name__}",
            )

    def _compact_grounding(self, semantic_grounding: dict[str, Any]) -> dict[str, Any]:
        candidate_models = []
        for item in (semantic_grounding.get("candidate_models") or [])[:6]:
            candidate_models.append(
                {
                    "name": item.get("name"),
                    "label": item.get("label"),
                    "description": item.get("description"),
                    "semantic_kind": item.get("semantic_kind"),
                    "semantic_domain": item.get("semantic_domain"),
                    "source_table": item.get("source_table"),
                    "entry_enabled": item.get("entry_enabled"),
                    "supports_entity_resolution": item.get("supports_entity_resolution"),
                    "business_terms": item.get("business_terms", [])[:8],
                    "dimensions": item.get("dimensions", [])[:10],
                    "metrics": item.get("metrics", [])[:10],
                    "analysis_patterns": item.get("analysis_patterns", [])[:6],
                    "has_yaml_definition": item.get("has_yaml_definition", False),
                }
            )

        catalog_by_kind: dict[str, list[dict[str, Any]]] = {}
        for key, items in (semantic_grounding.get("catalog_by_kind") or {}).items():
            catalog_by_kind[key] = [
                {
                    "name": item.get("name"),
                    "label": item.get("label"),
                    "semantic_domain": item.get("semantic_domain"),
                    "dimensions": item.get("dimensions", [])[:8],
                    "metrics": item.get("metrics", [])[:8],
                    "analysis_patterns": item.get("analysis_patterns", [])[:5],
                    "supports_entity_resolution": item.get("supports_entity_resolution"),
                }
                for item in (items or [])[:4]
            ]

        return {
            "heuristic_query_mode": semantic_grounding.get("heuristic_query_mode", "fact_query"),
            "company_fragments": semantic_grounding.get("company_fragments", []),
            "enterprise_candidates": semantic_grounding.get("enterprise_candidates", [])[:5],
            "query_keywords": semantic_grounding.get("query_keywords", [])[:20],
            "candidate_models": candidate_models,
            "catalog_by_kind": catalog_by_kind,
        }

    def _normalize_result(
        self,
        payload: dict[str, Any],
        semantic_grounding: dict[str, Any],
    ) -> UnderstandingResult:
        available_models = self._available_models(semantic_grounding)
        query_mode = str(payload.get("query_mode") or semantic_grounding.get("heuristic_query_mode") or "fact_query")
        entities_raw = payload.get("entities") if isinstance(payload.get("entities"), dict) else {}
        entities = {
            "enterprise_names": self._string_list(entities_raw.get("enterprise_names")),
            "taxpayer_ids": self._string_list(entities_raw.get("taxpayer_ids")),
            "tax_types": self._string_list(entities_raw.get("tax_types")),
            "periods": self._string_list(entities_raw.get("periods")),
        }

        semantic_scope = self._normalize_semantic_scope(
            payload.get("semantic_scope"),
            semantic_grounding,
            available_models,
        )
        candidate_models = self._normalize_candidate_models(
            payload.get("candidate_models"),
            semantic_scope,
            available_models,
        )

        intent_summary = str(payload.get("intent_summary") or "").strip()
        business_goal = str(payload.get("business_goal") or "").strip()
        if not intent_summary:
            intent_summary = business_goal or f"Identify the business intent for {query_mode}"
        if not business_goal:
            business_goal = intent_summary

        resolution_requirements = self._string_list(payload.get("resolution_requirements"))
        if entities["enterprise_names"] and not resolution_requirements:
            resolution_requirements = ["Resolve enterprise_name to taxpayer_id"]

        return UnderstandingResult(
            query_mode=query_mode,
            intent_summary=intent_summary,
            business_goal=business_goal,
            entities=entities,
            semantic_scope=semantic_scope,
            dimensions=self._string_list(payload.get("dimensions")),
            metrics=self._string_list(payload.get("metrics")),
            comparisons=self._comparison_list(payload.get("comparisons")),
            required_evidence=self._string_list(payload.get("required_evidence")),
            resolution_requirements=resolution_requirements,
            candidate_models=candidate_models,
            ambiguities=self._string_list(payload.get("ambiguities")),
            confidence=str(payload.get("confidence") or "medium").lower(),
        )

    def _build_fallback_result(
        self,
        user_query: str,
        semantic_grounding: dict[str, Any],
        *,
        failure_type: str = "",
        failure_message: str = "",
    ) -> UnderstandingResult:
        heuristic_mode = str(semantic_grounding.get("heuristic_query_mode") or "fact_query")
        enterprise_candidates = semantic_grounding.get("enterprise_candidates") or []
        periods = semantic_grounding.get("period_hints", {}).get("periods") or []
        available_models = self._available_models(semantic_grounding)
        semantic_scope = self._normalize_semantic_scope({}, semantic_grounding, available_models)
        enterprise_names = [
            item.get("enterprise_name")
            for item in enterprise_candidates
            if item.get("enterprise_name")
        ][:3]

        resolution_requirements: list[str] = []
        if enterprise_names:
            resolution_requirements.append("Resolve enterprise_name to taxpayer_id")

        return UnderstandingResult(
            query_mode=heuristic_mode,
            intent_summary=f"意图识别失败，已切换为启发式理解：{user_query[:60]}",
            business_goal=user_query[:160],
            entities={
                "enterprise_names": enterprise_names,
                "taxpayer_ids": [item.get("taxpayer_id") for item in enterprise_candidates if item.get("taxpayer_id")][:3],
                "tax_types": [],
                "periods": periods[:6],
            },
            semantic_scope=semantic_scope,
            candidate_models=self._normalize_candidate_models([], semantic_scope, available_models),
            resolution_requirements=resolution_requirements,
            confidence="low",
        )

    def _classify_failure_type(self, exc: Exception) -> str:
        name = type(exc).__name__
        mapping = {
            "APIConnectionError": "llm_connection_failed",
            "APITimeoutError": "llm_transport_timeout",
            "CancelledError": "llm_cancelled",
        }
        return mapping.get(name, "llm_call_failed")

    def _build_failure_message(self, exc: Exception) -> str:
        name = type(exc).__name__
        detail = str(exc or "").strip()
        if name == "APIConnectionError":
            prefix = "意图识别调用失败，模型服务连接异常。"
        elif name == "APITimeoutError":
            prefix = "意图识别调用失败，模型服务请求超时。"
        elif name == "CancelledError":
            prefix = "意图识别调用被取消。"
        else:
            prefix = f"意图识别调用失败：{name}。"
        if not detail:
            return prefix
        return f"{prefix} {detail[:200]}"

    def _finalize_fallback_result(
        self,
        result: UnderstandingResult,
        *,
        user_query: str,
        failure_type: str,
        failure_message: str,
    ) -> UnderstandingResult:
        result.intent_summary = f"意图识别失败，已切换为启发式理解：{user_query[:60]}"
        result.used_fallback = True
        result.failure_type = failure_type.strip()
        result.failure_message = failure_message.strip()
        return result

    def _available_models(self, semantic_grounding: dict[str, Any]) -> dict[str, str]:
        available: dict[str, str] = {}
        for item in semantic_grounding.get("candidate_models", []) or []:
            name = str(item.get("name") or "").strip()
            kind = str(item.get("semantic_kind") or "").strip()
            if name:
                available[name] = kind
        return available

    def _normalize_semantic_scope(
        self,
        value: Any,
        semantic_grounding: dict[str, Any],
        available_models: dict[str, str],
    ) -> dict[str, list[str]]:
        catalog = semantic_grounding.get("catalog_by_kind") or {}
        scope: dict[str, list[str]] = {key: [] for key in SEMANTIC_SCOPE_KEYS}

        if isinstance(value, dict):
            for key in SEMANTIC_SCOPE_KEYS:
                model_names = self._string_list(value.get(key))
                expected_kind = self._scope_key_to_kind(key)
                scope[key] = [
                    name
                    for name in model_names
                    if available_models.get(name) == expected_kind
                ]

        if not any(scope.values()):
            for key in SEMANTIC_SCOPE_KEYS:
                kind = self._scope_key_to_kind(key)
                scope[key] = [
                    str(item.get("name") or "")
                    for item in (catalog.get(kind) or [])[:3]
                    if str(item.get("name") or "").strip()
                ]

        return scope

    def _normalize_candidate_models(
        self,
        value: Any,
        semantic_scope: dict[str, list[str]],
        available_models: dict[str, str],
    ) -> list[str]:
        ordered: list[str] = []
        for name in self._string_list(value):
            if name in available_models and name not in ordered:
                ordered.append(name)

        for name in self._flatten_semantic_scope(semantic_scope):
            if name not in ordered:
                ordered.append(name)
        if not ordered:
            ordered.extend(list(available_models.keys())[:3])
        return ordered[:8]

    def _flatten_semantic_scope(self, semantic_scope: dict[str, list[str]]) -> list[str]:
        ordered: list[str] = []
        for key in ("composite_models", "atomic_models", "entity_models"):
            for name in semantic_scope.get(key, []):
                if name and name not in ordered:
                    ordered.append(name)
        return ordered

    def _scope_key_to_kind(self, key: str) -> str:
        return {
            "entity_models": "entity_dimension",
            "atomic_models": "atomic_fact",
            "composite_models": "composite_analysis",
        }.get(key, "")

    def _string_list(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        result: list[str] = []
        for item in value:
            text = str(item or "").strip()
            if text and text not in result:
                result.append(text)
        return result[:12]

    def _comparison_list(self, value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        items: list[dict[str, Any]] = []
        for item in value[:6]:
            if not isinstance(item, dict):
                continue
            left = str(item.get("left") or "").strip()
            right = str(item.get("right") or "").strip()
            operator = str(item.get("operator") or "").strip()
            if not left and not right:
                continue
            items.append({"left": left, "right": right, "operator": operator or "compare"})
        return items
