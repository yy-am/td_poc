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
from app.semantic.compiler import load_semantic_definition


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text and text not in items:
            items.append(text)
    return items


def _extract_model_metadata(
    *,
    name: str,
    label: str,
    description: str,
    source_table: str,
    yaml_definition: str | None,
    status: str,
) -> dict[str, Any]:
    metadata = {
        "name": name,
        "label": label,
        "description": description or "",
        "source_table": source_table,
        "status": status,
        "has_yaml_definition": bool((yaml_definition or "").strip()),
        "recommended_tool": "semantic_query" if (yaml_definition or "").strip() else "sql_executor",
        "business_terms": [],
        "intent_aliases": [],
        "dimensions": [],
        "metrics": [],
        "analysis_patterns": [],
        "time": {},
        "entities": {},
    }

    if not yaml_definition:
        return metadata

    try:
        loaded = load_semantic_definition(yaml_definition)
    except Exception:
        return metadata

    metadata["business_terms"] = _string_list(loaded.get("business_terms"))
    metadata["intent_aliases"] = _string_list(loaded.get("intent_aliases"))
    metadata["analysis_patterns"] = _string_list(loaded.get("analysis_patterns"))
    metadata["time"] = loaded.get("time") if isinstance(loaded.get("time"), dict) else {}
    metadata["entities"] = loaded.get("entities") if isinstance(loaded.get("entities"), dict) else {}

    for item in loaded.get("dimensions", []) or []:
        if isinstance(item, str):
            metadata["dimensions"].append(item)
            continue
        if not isinstance(item, dict):
            continue
        for key in ("name", "label", "column"):
            value = str(item.get(key) or "").strip()
            if value and value not in metadata["dimensions"]:
                metadata["dimensions"].append(value)

    for item in loaded.get("metrics", []) or []:
        if isinstance(item, str):
            metadata["metrics"].append(item)
            continue
        if not isinstance(item, dict):
            continue
        for key in ("name", "label", "column"):
            value = str(item.get(key) or "").strip()
            if value and value not in metadata["metrics"]:
                metadata["metrics"].append(value)

    return metadata


def _score_model(
    user_query: str,
    model: dict[str, Any],
    query_keywords: list[str],
    understanding_result: dict[str, Any] | None,
) -> tuple[int, list[str]]:
    matched: list[str] = []
    score = 0
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
        if any(word in model.get("analysis_patterns", []) for word in ("compare", "reconciliation", "diagnosis")):
            score += 4

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
                SysSemanticModel.yaml_definition,
                SysSemanticModel.status,
            ).where(SysSemanticModel.status == "active")
        )

        models: list[dict[str, Any]] = []
        for name, label, description, source_table, yaml_definition, status in model_result.all():
            item = _extract_model_metadata(
                name=name,
                label=label,
                description=description or "",
                source_table=source_table,
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

    models.sort(key=lambda item: (-item["score"], item["name"]))
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

    return {
        "heuristic_query_mode": heuristic_mode["query_mode"],
        "heuristic_confidence": heuristic_mode["confidence"],
        "period_hints": period_hints,
        "query_keywords": query_keywords,
        "company_fragments": company_fragments,
        "enterprise_candidates": enterprise_candidates[:5],
        "candidate_models": candidate_models,
        "relevant_tables": relevant_tables,
        "relevant_table_schemas": relevant_table_schemas,
    }
