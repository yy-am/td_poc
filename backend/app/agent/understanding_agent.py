"""LLM-based business understanding layer for agent orchestration."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from app.agent.planner import parse_plan_json, trim_conversation_history
from app.agent.prompts.understanding_prompt_v1 import UNDERSTANDING_SYSTEM_PROMPT

ALLOWED_QUERY_MODES = {"metadata", "fact_query", "analysis", "reconciliation", "diagnosis"}
ALLOWED_CONFIDENCE = {"low", "medium", "high"}


class UnderstandingResult:
    """Normalized result produced by the understanding layer."""

    __slots__ = (
        "query_mode",
        "intent_summary",
        "business_goal",
        "entities",
        "dimensions",
        "metrics",
        "comparisons",
        "required_evidence",
        "candidate_models",
        "ambiguities",
        "confidence",
    )

    def __init__(
        self,
        query_mode: str = "fact_query",
        intent_summary: str = "",
        business_goal: str = "",
        entities: dict[str, Any] | None = None,
        dimensions: list[str] | None = None,
        metrics: list[str] | None = None,
        comparisons: list[dict[str, Any]] | None = None,
        required_evidence: list[str] | None = None,
        candidate_models: list[str] | None = None,
        ambiguities: list[str] | None = None,
        confidence: str = "medium",
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
        self.dimensions = dimensions or []
        self.metrics = metrics or []
        self.comparisons = comparisons or []
        self.required_evidence = required_evidence or []
        self.candidate_models = candidate_models or []
        self.ambiguities = ambiguities or []
        self.confidence = confidence if confidence in ALLOWED_CONFIDENCE else "medium"

    def to_dict(self) -> dict[str, Any]:
        return {
            "query_mode": self.query_mode,
            "intent_summary": self.intent_summary,
            "business_goal": self.business_goal,
            "entities": self.entities,
            "dimensions": self.dimensions,
            "metrics": self.metrics,
            "comparisons": self.comparisons,
            "required_evidence": self.required_evidence,
            "candidate_models": self.candidate_models,
            "ambiguities": self.ambiguities,
            "confidence": self.confidence,
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
                    stream=False,
                    temperature=0.0,
                    max_tokens=900,
                    response_format={"type": "json_object"},
                ),
                timeout=30,
            )
            raw_content = response.choices[0].message.content or ""
            parsed = parse_plan_json(raw_content)
            return self._normalize_result(parsed, semantic_grounding)
        except Exception:
            return self._build_fallback_result(user_query, semantic_grounding)

    def _compact_grounding(self, semantic_grounding: dict[str, Any]) -> dict[str, Any]:
        candidate_models = []
        for item in (semantic_grounding.get("candidate_models") or [])[:6]:
            candidate_models.append(
                {
                    "name": item.get("name"),
                    "label": item.get("label"),
                    "description": item.get("description"),
                    "source_table": item.get("source_table"),
                    "business_terms": item.get("business_terms", [])[:8],
                    "dimensions": item.get("dimensions", [])[:10],
                    "metrics": item.get("metrics", [])[:10],
                    "analysis_patterns": item.get("analysis_patterns", [])[:6],
                    "has_yaml_definition": item.get("has_yaml_definition", False),
                }
            )

        return {
            "heuristic_query_mode": semantic_grounding.get("heuristic_query_mode", "fact_query"),
            "company_fragments": semantic_grounding.get("company_fragments", []),
            "enterprise_candidates": semantic_grounding.get("enterprise_candidates", [])[:5],
            "query_keywords": semantic_grounding.get("query_keywords", [])[:20],
            "candidate_models": candidate_models,
        }

    def _normalize_result(
        self,
        payload: dict[str, Any],
        semantic_grounding: dict[str, Any],
    ) -> UnderstandingResult:
        available_model_names = {
            str(item.get("name"))
            for item in semantic_grounding.get("candidate_models", [])
            if item.get("name")
        }
        query_mode = str(payload.get("query_mode") or semantic_grounding.get("heuristic_query_mode") or "fact_query")
        entities_raw = payload.get("entities") if isinstance(payload.get("entities"), dict) else {}
        entities = {
            "enterprise_names": self._string_list(entities_raw.get("enterprise_names")),
            "taxpayer_ids": self._string_list(entities_raw.get("taxpayer_ids")),
            "tax_types": self._string_list(entities_raw.get("tax_types")),
            "periods": self._string_list(entities_raw.get("periods")),
        }

        candidate_models = [
            name
            for name in self._string_list(payload.get("candidate_models"))
            if name in available_model_names
        ]
        if not candidate_models:
            candidate_models = [
                item["name"]
                for item in semantic_grounding.get("candidate_models", [])[:3]
                if item.get("name")
            ]

        intent_summary = str(payload.get("intent_summary") or "").strip()
        business_goal = str(payload.get("business_goal") or "").strip()
        if not intent_summary:
            intent_summary = business_goal or f"识别当前问题属于{query_mode}"
        if not business_goal:
            business_goal = intent_summary

        return UnderstandingResult(
            query_mode=query_mode,
            intent_summary=intent_summary,
            business_goal=business_goal,
            entities=entities,
            dimensions=self._string_list(payload.get("dimensions")),
            metrics=self._string_list(payload.get("metrics")),
            comparisons=self._comparison_list(payload.get("comparisons")),
            required_evidence=self._string_list(payload.get("required_evidence")),
            candidate_models=candidate_models,
            ambiguities=self._string_list(payload.get("ambiguities")),
            confidence=str(payload.get("confidence") or "medium").lower(),
        )

    def _build_fallback_result(
        self,
        user_query: str,
        semantic_grounding: dict[str, Any],
    ) -> UnderstandingResult:
        heuristic_mode = str(semantic_grounding.get("heuristic_query_mode") or "fact_query")
        enterprise_candidates = semantic_grounding.get("enterprise_candidates") or []
        periods = semantic_grounding.get("period_hints", {}).get("periods") or []
        return UnderstandingResult(
            query_mode=heuristic_mode,
            intent_summary=f"基于候选语义资产理解用户问题：{user_query[:40]}",
            business_goal=user_query[:120],
            entities={
                "enterprise_names": [item.get("enterprise_name") for item in enterprise_candidates if item.get("enterprise_name")][:3],
                "taxpayer_ids": [item.get("taxpayer_id") for item in enterprise_candidates if item.get("taxpayer_id")][:3],
                "tax_types": [],
                "periods": periods[:6],
            },
            candidate_models=[
                item["name"]
                for item in semantic_grounding.get("candidate_models", [])[:3]
                if item.get("name")
            ],
            confidence="low",
        )

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
