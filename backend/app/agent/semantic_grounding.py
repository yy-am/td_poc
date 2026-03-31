"""Semantic asset retrieval used before LLM understanding."""

from __future__ import annotations

from typing import Any

from sqlalchemy import inspect, select

from app.agent.runtime_context import (
    _collect_query_keywords,
    _load_table_schema_map,
    classify_query_mode,
    extract_company_fragments,
    extract_period_hints,
)
from app.database import AsyncSessionLocal
from app.models.enterprise import EnterpriseInfo
from app.models.semantic import SysSemanticModel
from app.semantic.compiler_v2 import SemanticDefinitionError, load_semantic_definition, normalize_definition
from app.semantic.catalog import extract_semantic_metadata


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text and text not in items:
            items.append(text)
    return items


def _flatten_semantic_terms(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []

    items: list[str] = []
    for item in value:
        if isinstance(item, dict):
            for key in ("name", "label", "column"):
                text = str(item.get(key) or "").strip()
                if text and text not in items:
                    items.append(text)
            continue
        text = str(item or "").strip()
        if text and text not in items:
            items.append(text)
    return items


def _semantic_term_pairs(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []

    terms: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in value:
        if isinstance(item, dict):
            name = str(item.get("name") or item.get("column") or "").strip()
            label = str(item.get("label") or "").strip()
        else:
            text = str(item or "").strip()
            if not text:
                continue
            name = text
            label = ""

        key = name or label
        if not key or key in seen:
            continue
        seen.add(key)
        terms.append(
            {
                "name": name,
                "label": label,
            }
        )
    return terms


def _extract_model_metadata(
    *,
    name: str,
    label: str,
    description: str,
    source_table: str,
    model_type: str = "physical",
    yaml_definition: str | None,
    status: str,
) -> dict[str, Any]:
    metadata = extract_semantic_metadata(
        name=name,
        label=label,
        description=description,
        source_table=source_table,
        model_type=model_type,
        yaml_definition=yaml_definition,
        status=status,
    )
    if metadata["has_yaml_definition"]:
        preferred_lane = str((metadata.get("query_hints") or {}).get("preferred_lane") or "").strip().lower()
        if metadata.get("semantic_kind") == "composite_analysis" and preferred_lane == "metric":
            metadata["recommended_tool"] = "mql_query"
        else:
            metadata["recommended_tool"] = "semantic_query"
    else:
        metadata["recommended_tool"] = "sql_executor"
    metadata["intent_aliases"] = _string_list(metadata.get("intent_aliases"))
    metadata["analysis_patterns"] = _string_list(metadata.get("analysis_patterns"))
    metadata["business_terms"] = _string_list(metadata.get("business_terms"))

    try:
        normalized = normalize_definition(
            load_semantic_definition(yaml_definition),
            fallback_name=name,
            fallback_label=label,
            fallback_table=source_table,
        )
        metadata["dimension_terms"] = _semantic_term_pairs(normalized.get("dimensions"))
        metadata["metric_terms"] = _semantic_term_pairs(normalized.get("metrics"))
        metadata["dimensions"] = _flatten_semantic_terms(normalized.get("dimensions"))
        metadata["metrics"] = _flatten_semantic_terms(normalized.get("metrics"))
        metadata["detail_fields"] = (
            list(normalized.get("detail_fields") or [])
            if isinstance(normalized.get("detail_fields"), list)
            else []
        )
    except SemanticDefinitionError:
        metadata["dimension_terms"] = []
        metadata["metric_terms"] = []
        metadata["dimensions"] = []
        metadata["metrics"] = []

    return metadata


def _is_entry_enabled(model: dict[str, Any]) -> bool:
    if not model.get("has_yaml_definition"):
        return True
    return bool(model.get("entry_enabled", True))


def _score_model(
    user_query: str,
    model: dict[str, Any],
    query_keywords: list[str],
    understanding_result: dict[str, Any] | None,
) -> tuple[int, list[str]]:
    matched: list[str] = []
    score = 0
    query_text = str(user_query or "").strip().lower()
    entry_enabled = _is_entry_enabled(model)
    matched_intent_signal = False
    haystack = " ".join(
        [
            model.get("name", ""),
            model.get("label", ""),
            model.get("description", ""),
            model.get("source_table", ""),
            " ".join(model.get("business_terms", [])),
            " ".join(model.get("intent_aliases", [])),
            " ".join(model.get("dimensions", [])),
            " ".join(model.get("metrics", [])),
            " ".join(model.get("analysis_patterns", [])),
        ]
    ).lower()

    for keyword in query_keywords:
        token = str(keyword or "").strip().lower()
        if not token:
            continue
        if token in haystack:
            score += 3 if len(token) >= 3 else 1
            matched.append(keyword)

    phrase_terms = (
        _string_list(model.get("business_terms"))
        + _string_list(model.get("intent_aliases"))
        + _string_list(model.get("analysis_patterns"))
    )
    for phrase in phrase_terms:
        token = str(phrase or "").strip().lower()
        if len(token) < 3:
            continue
        if token in query_text and phrase not in matched:
            score += 4
            matched.append(phrase)
            if phrase in _string_list(model.get("intent_aliases")) or phrase in _string_list(model.get("analysis_patterns")):
                matched_intent_signal = True

    understanding_result = understanding_result or {}
    candidate_models = {str(name) for name in understanding_result.get("candidate_models", [])}
    if model.get("name") in candidate_models:
        score += 6

    for name in understanding_result.get("metrics", []) or []:
        if str(name) in model.get("metrics", []):
            score += 4
    for name in understanding_result.get("dimensions", []) or []:
        if str(name) in model.get("dimensions", []):
            score += 3

    query_mode = str(understanding_result.get("query_mode") or classify_query_mode(user_query)["query_mode"])
    if query_mode in {"analysis", "reconciliation", "diagnosis"}:
        if model.get("semantic_kind") == "composite_analysis":
            score += 5
        if model.get("semantic_kind") == "atomic_fact":
            score += 2
        if any(word in model.get("analysis_patterns", []) for word in ("compare", "reconciliation", "diagnosis")):
            score += 4
        if model.get("recommended_tool") == "mql_query":
            score += 2
        if entry_enabled and model.get("semantic_kind") == "composite_analysis":
            score += 2
        elif not entry_enabled:
            score -= 1 if matched_intent_signal else 6
    elif query_mode == "fact_query":
        if model.get("semantic_kind") == "atomic_fact":
            score += 4
        if not entry_enabled and model.get("semantic_kind") == "composite_analysis" and not matched_intent_signal:
            score -= 3
    if matched_intent_signal and model.get("semantic_kind") == "composite_analysis":
        score += 4
    if model.get("semantic_kind") == "entity_dimension" and model.get("supports_entity_resolution"):
        score += 2

    return score, matched


def _merge_company_fragments(
    user_query: str,
    understanding_result: dict[str, Any] | None,
) -> list[str]:
    fragments = extract_company_fragments(user_query)
    entities = (understanding_result or {}).get("entities") or {}
    for name in entities.get("enterprise_names", []) or []:
        value = str(name or "").strip()
        if value and value not in fragments:
            fragments.append(value)
    return fragments[:5]


def _merge_query_keywords(
    user_query: str,
    understanding_result: dict[str, Any] | None,
) -> list[str]:
    keywords = _collect_query_keywords(user_query)
    understanding_result = understanding_result or {}
    for key in ("metrics", "dimensions", "candidate_models"):
        for value in understanding_result.get(key, []) or []:
            text = str(value or "").strip()
            if text and text not in keywords:
                keywords.append(text)
    semantic_scope = understanding_result.get("semantic_scope") or {}
    for key in ("entity_models", "atomic_models", "composite_models"):
        for value in semantic_scope.get(key, []) or []:
            text = str(value or "").strip()
            if text and text not in keywords:
                keywords.append(text)
    for value in ((understanding_result.get("entities") or {}).get("enterprise_names") or []):
        text = str(value or "").strip()
        if text and text not in keywords:
            keywords.append(text)
    goal = str(understanding_result.get("business_goal") or "").strip()
    if goal and goal not in keywords:
        keywords.append(goal)
    return keywords[:30]


async def build_semantic_grounding(
    user_query: str,
    understanding_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    heuristic_mode = classify_query_mode(user_query)
    query_keywords = _merge_query_keywords(user_query, understanding_result)
    company_fragments = _merge_company_fragments(user_query, understanding_result)
    period_hints = extract_period_hints(user_query)

    async with AsyncSessionLocal() as db:
        model_result = await db.execute(
            select(
                SysSemanticModel.name,
                SysSemanticModel.label,
                SysSemanticModel.description,
                SysSemanticModel.source_table,
                SysSemanticModel.model_type,
                SysSemanticModel.yaml_definition,
                SysSemanticModel.status,
            ).where(SysSemanticModel.status == "active")
        )

        models: list[dict[str, Any]] = []
        for name, label, description, source_table, model_type, yaml_definition, status in model_result.all():
            item = _extract_model_metadata(
                name=name,
                label=label,
                description=description or "",
                source_table=source_table,
                model_type=model_type,
                yaml_definition=yaml_definition,
                status=status,
            )
            score, matched = _score_model(user_query, item, query_keywords, understanding_result)
            item["score"] = score
            item["matched_keywords"] = matched
            models.append(item)

        conn = await db.connection()
        table_names = await conn.run_sync(lambda sync_conn: sorted(inspect(sync_conn).get_table_names()))

        enterprise_candidates: list[dict[str, str]] = []
        for fragment in company_fragments:
            enterprise_result = await db.execute(
                select(EnterpriseInfo.enterprise_name, EnterpriseInfo.taxpayer_id)
                .where(EnterpriseInfo.enterprise_name.like(f"{fragment}%"))
                .limit(5)
            )
            for enterprise_name, taxpayer_id in enterprise_result.all():
                item = {"enterprise_name": enterprise_name, "taxpayer_id": taxpayer_id}
                if item not in enterprise_candidates:
                    enterprise_candidates.append(item)

    models.sort(key=lambda item: (-item["score"], not _is_entry_enabled(item), item["name"]))
    candidate_models = [item for item in models if item["score"] > 0][:6]
    if not candidate_models:
        candidate_models = models[:3]

    relevant_table_names: list[str] = []
    for model in candidate_models:
        table_name = model.get("source_table")
        if table_name and table_name not in relevant_table_names:
            relevant_table_names.append(table_name)

    for table_name in table_names:
        lower_table = str(table_name).lower()
        if any(str(keyword).lower() in lower_table for keyword in query_keywords):
            if table_name not in relevant_table_names:
                relevant_table_names.append(table_name)

    if enterprise_candidates and "enterprise_info" not in relevant_table_names:
        relevant_table_names.append("enterprise_info")

    relevant_tables = relevant_table_names[:8]
    async with AsyncSessionLocal() as db:
        conn = await db.connection()
        relevant_table_schemas = await _load_table_schema_map(conn, relevant_tables)

    catalog_by_kind = {
        "entity_dimension": [item for item in candidate_models if item.get("semantic_kind") == "entity_dimension"],
        "atomic_fact": [item for item in candidate_models if item.get("semantic_kind") == "atomic_fact"],
        "composite_analysis": [item for item in candidate_models if item.get("semantic_kind") == "composite_analysis"],
    }

    return {
        "heuristic_query_mode": heuristic_mode["query_mode"],
        "heuristic_confidence": heuristic_mode["confidence"],
        "period_hints": period_hints,
        "query_keywords": query_keywords,
        "company_fragments": company_fragments,
        "enterprise_candidates": enterprise_candidates[:5],
        "candidate_models": candidate_models,
        "catalog_by_kind": catalog_by_kind,
        "relevant_tables": relevant_tables,
        "relevant_table_schemas": relevant_table_schemas,
    }
