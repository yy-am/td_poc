"""Semantic catalog helpers shared by API, grounding, and seeds."""

from __future__ import annotations

from typing import Any

from .compiler_v2 import SemanticDefinitionError, load_semantic_definition, normalize_definition

KIND_TO_MODEL_TYPE = {
    "entity_dimension": "semantic",
    "atomic_fact": "physical",
    "composite_analysis": "metric",
}

MODEL_TYPE_TO_KIND = {
    "physical": "atomic_fact",
    "semantic": "entity_dimension",
    "metric": "composite_analysis",
}


def infer_model_type_from_kind(kind: str) -> str:
    return KIND_TO_MODEL_TYPE.get(kind, "semantic")


def extract_semantic_metadata(
    *,
    name: str,
    label: str,
    description: str,
    source_table: str,
    model_type: str,
    yaml_definition: str | None,
    status: str,
) -> dict[str, Any]:
    metadata = {
        "name": name,
        "label": label,
        "description": description or "",
        "source_table": source_table,
        "model_type": model_type,
        "status": status,
        "has_yaml_definition": bool((yaml_definition or "").strip()),
        "semantic_kind": MODEL_TYPE_TO_KIND.get(model_type, "atomic_fact"),
        "semantic_domain": "general",
        "semantic_grain": "",
        "entry_enabled": False,
        "source_count": 1 if source_table else 0,
        "join_count": 0,
        "business_terms": [],
        "intent_aliases": [],
        "analysis_patterns": [],
        "evidence_requirements": [],
        "fallback_policy": "fallback_to_sql",
        "dimensions": [],
        "metrics": [],
        "entities": {},
        "time": {},
        "supports_entity_resolution": False,
        "relationship_graph": [],
        "metric_lineage": [],
        "detail_fields": [],
        "materialization_policy": {},
        "query_hints": {},
    }

    if not metadata["has_yaml_definition"]:
        return metadata

    try:
        loaded = load_semantic_definition(yaml_definition)
        normalized = normalize_definition(
            loaded,
            fallback_name=name,
            fallback_label=label,
            fallback_table=source_table,
        )
    except SemanticDefinitionError:
        return metadata

    metadata["semantic_kind"] = str(normalized.get("kind") or metadata["semantic_kind"])
    metadata["semantic_domain"] = str(normalized.get("domain") or metadata["semantic_domain"])
    metadata["semantic_grain"] = str(normalized.get("grain") or "")
    metadata["entry_enabled"] = bool(normalized.get("entry_enabled", True))
    metadata["source_count"] = len(normalized.get("sources") or [])
    metadata["join_count"] = len(normalized.get("joins") or [])
    metadata["business_terms"] = list(normalized.get("business_terms") or [])
    metadata["intent_aliases"] = list(normalized.get("intent_aliases") or [])
    metadata["analysis_patterns"] = list(normalized.get("analysis_patterns") or [])
    metadata["evidence_requirements"] = list(normalized.get("evidence_requirements") or [])
    metadata["fallback_policy"] = str(normalized.get("fallback_policy") or "fallback_to_sql")
    metadata["dimensions"] = [str(item.get("name") or "") for item in normalized.get("dimensions", []) if item.get("name")]
    metadata["metrics"] = [str(item.get("name") or "") for item in normalized.get("metrics", []) if item.get("name")]
    metadata["entities"] = normalized.get("entities") if isinstance(normalized.get("entities"), dict) else {}
    metadata["time"] = normalized.get("time") if isinstance(normalized.get("time"), dict) else {}
    metadata["relationship_graph"] = (
        normalized.get("relationship_graph") if isinstance(normalized.get("relationship_graph"), list) else []
    )
    metadata["metric_lineage"] = (
        normalized.get("metric_lineage") if isinstance(normalized.get("metric_lineage"), list) else []
    )
    metadata["detail_fields"] = normalized.get("detail_fields") if isinstance(normalized.get("detail_fields"), list) else []
    metadata["materialization_policy"] = (
        normalized.get("materialization_policy")
        if isinstance(normalized.get("materialization_policy"), dict)
        else {}
    )
    metadata["query_hints"] = normalized.get("query_hints") if isinstance(normalized.get("query_hints"), dict) else {}
    metadata["supports_entity_resolution"] = any(
        isinstance(spec, dict) and isinstance(spec.get("resolver"), dict)
        for spec in metadata["entities"].values()
    )

    return metadata
