"""Semantic query execution service with entity resolution and multi-source support."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.semantic import SysSemanticModel
from app.schemas.semantic import SemanticQueryRequest, SemanticQueryResponse

from .compiler_v2 import (
    SemanticDefinitionError,
    compile_semantic_query,
    load_semantic_definition,
    normalize_definition,
    quote_identifier,
)


async def semantic_query(
    model_name: str | None = None,
    model_id: int | None = None,
    dimensions: list[str] | None = None,
    metrics: list[str] | None = None,
    filters: list[dict[str, Any]] | None = None,
    order: list[dict[str, Any]] | None = None,
    limit: int = 100,
    entity_filters: dict[str, Any] | None = None,
    resolved_filters: dict[str, Any] | None = None,
    grain: str | None = None,
    db: AsyncSession | None = None,
) -> dict[str, Any]:
    """Execute a semantic query from the registered YAML definition."""

    request = SemanticQueryRequest(
        model_name=model_name,
        model_id=model_id,
        dimensions=dimensions or [],
        metrics=metrics or [],
        filters=filters or [],
        order=order or [],
        limit=limit,
        entity_filters=entity_filters or {},
        resolved_filters=resolved_filters or {},
        grain=grain,
    )

    if db is None:
        async with AsyncSessionLocal() as session:
            return await _semantic_query_with_session(session, request)
    return await _semantic_query_with_session(db, request)


async def _semantic_query_with_session(db: AsyncSession, request: SemanticQueryRequest) -> dict[str, Any]:
    model = await _load_semantic_model(db, request)
    normalized = await _resolve_model_definition(db, model, seen=set())
    filter_context = await _resolve_filter_context(db, normalized, request)

    compiled = compile_semantic_query(
        definition=normalized,
        model_name=model.name,
        model_label=model.label,
        request_dimensions=request.dimensions,
        request_metrics=request.metrics,
        filters=filter_context["filters"],
        order=[item.model_dump() for item in request.order],
        limit=request.limit,
    )

    result = await db.execute(text(compiled.sql), compiled.params)
    columns = list(result.keys())
    rows = [dict(row) for row in result.mappings().all()]

    response = SemanticQueryResponse(
        model_id=model.id,
        model_name=model.name,
        model_label=model.label,
        source_table=compiled.source_table,
        sql=compiled.sql,
        columns=columns,
        rows=rows,
        row_count=len(rows),
        selected_dimensions=compiled.selected_dimensions,
        selected_metrics=compiled.selected_metrics,
        warnings=compiled.warnings,
        resolved_filters=filter_context["resolved_filter_map"],
        resolution_log=filter_context["resolution_log"],
        semantic_kind=str(normalized.get("kind") or ""),
        semantic_domain=str(normalized.get("domain") or ""),
        semantic_grain=str(request.grain or normalized.get("grain") or ""),
    )
    return response.model_dump()


async def _load_semantic_model(db: AsyncSession, request: SemanticQueryRequest) -> SysSemanticModel:
    if request.model_id is None and not request.model_name:
        raise SemanticDefinitionError("semantic_query requires model_id or model_name")

    stmt = select(SysSemanticModel)
    if request.model_id is not None:
        stmt = stmt.where(SysSemanticModel.id == request.model_id)
    else:
        stmt = stmt.where(SysSemanticModel.name == request.model_name)

    result = await db.execute(stmt)
    model = result.scalar_one_or_none()
    if model is None:
        raise SemanticDefinitionError("semantic model not found")
    if not model.yaml_definition:
        raise SemanticDefinitionError(f"semantic model {model.name} has no yaml_definition")
    if model.status != "active":
        raise SemanticDefinitionError(f"semantic model {model.name} is not active")
    return model


async def _load_semantic_model_by_name(db: AsyncSession, model_name: str) -> SysSemanticModel:
    result = await db.execute(select(SysSemanticModel).where(SysSemanticModel.name == model_name))
    model = result.scalar_one_or_none()
    if model is None:
        raise SemanticDefinitionError(f"semantic model {model_name} not found")
    if not model.yaml_definition:
        raise SemanticDefinitionError(f"semantic model {model_name} has no yaml_definition")
    if model.status != "active":
        raise SemanticDefinitionError(f"semantic model {model_name} is not active")
    return model


async def _resolve_model_definition(
    db: AsyncSession,
    model: SysSemanticModel,
    seen: set[str],
) -> dict[str, Any]:
    if model.name in seen:
        raise SemanticDefinitionError(f"检测到循环语义模型引用: {model.name}")
    seen.add(model.name)

    definition = load_semantic_definition(model.yaml_definition)
    normalized = normalize_definition(
        definition,
        fallback_name=model.name,
        fallback_label=model.label,
        fallback_table=model.source_table,
    )

    resolved_sources: list[dict[str, str]] = []
    for source in normalized.get("sources", []):
        if source.get("table"):
            resolved_sources.append(source)
            continue
        ref_name = str(source.get("model") or "").strip()
        if not ref_name:
            raise SemanticDefinitionError(f"{model.name} 存在未声明 model/table 的 source")
        ref_model = await _load_semantic_model_by_name(db, ref_name)
        ref_def = await _resolve_model_definition(db, ref_model, seen=seen.copy())
        ref_sources = ref_def.get("sources") or []
        if len(ref_sources) != 1 or ref_def.get("joins"):
            raise SemanticDefinitionError(f"暂不支持将复合语义模型 {ref_name} 作为 source 引入")
        ref_source = dict(ref_sources[0])
        ref_source["alias"] = source.get("alias") or ref_source.get("alias")
        resolved_sources.append(ref_source)

    normalized["sources"] = resolved_sources
    return normalized


async def _resolve_filter_context(
    db: AsyncSession,
    definition: dict[str, Any],
    request: SemanticQueryRequest,
) -> dict[str, Any]:
    filters: list[dict[str, Any]] = []
    resolution_log: list[str] = []
    resolved_filter_map: dict[str, list[Any]] = {}

    for field, value in (request.resolved_filters or {}).items():
        _append_resolved_filter(filters, resolved_filter_map, field, value)
        resolution_log.append(f"直接采用 resolved_filters.{field} 作为执行过滤条件。")

    for field, value in (request.entity_filters or {}).items():
        await _resolve_entity_filter(
            db,
            definition,
            field=field,
            value=value,
            filters=filters,
            resolved_filter_map=resolved_filter_map,
            resolution_log=resolution_log,
        )

    for item in request.filters:
        filter_dict = item.model_dump()
        field = str(filter_dict.get("field") or "").strip()
        if not field:
            continue
        handled = await _resolve_entity_filter(
            db,
            definition,
            field=field,
            value=filter_dict.get("value"),
            filters=filters,
            resolved_filter_map=resolved_filter_map,
            resolution_log=resolution_log,
            op=str(filter_dict.get("op") or "eq"),
            keep_original_on_fail=True,
        )
        if not handled:
            filters.append(filter_dict)

    return {
        "filters": filters,
        "resolved_filter_map": resolved_filter_map,
        "resolution_log": resolution_log,
    }


async def _resolve_entity_filter(
    db: AsyncSession,
    definition: dict[str, Any],
    *,
    field: str,
    value: Any,
    filters: list[dict[str, Any]],
    resolved_filter_map: dict[str, list[Any]],
    resolution_log: list[str],
    op: str = "eq",
    keep_original_on_fail: bool = False,
) -> bool:
    resolver_spec = _find_entity_resolver(definition, field)
    if resolver_spec is None:
        return False

    resolved_field = str(resolver_spec.get("output_field") or "").strip()
    if not resolved_field:
        return False

    resolved_values = await _lookup_resolved_values(
        db,
        resolver_spec=resolver_spec,
        input_field=field,
        raw_value=value,
    )
    if resolved_values:
        _append_resolved_filter(filters, resolved_filter_map, resolved_field, resolved_values)
        resolution_log.append(
            f"已将业务过滤 {field} 解析为 {resolved_field}，共命中 {len(resolved_values)} 个值。"
        )
        return True

    if keep_original_on_fail:
        filters.append({"field": field, "op": op, "value": value})
        resolution_log.append(f"未能解析 {field}，保留原始过滤条件继续执行。")
        return True

    return False


def _find_entity_resolver(definition: dict[str, Any], field: str) -> dict[str, Any] | None:
    entities = definition.get("entities") or {}
    for entity_name, spec in entities.items():
        if not isinstance(spec, dict):
            continue
        resolver = spec.get("resolver")
        input_fields = list((resolver or {}).get("input_fields") or [])
        if field in input_fields:
            merged = dict(resolver or {})
            merged.setdefault("entity_name", entity_name)
            merged.setdefault("display_field", spec.get("display_field"))
            merged.setdefault("primary_key", spec.get("primary_key"))
            return merged
    return None


async def _lookup_resolved_values(
    db: AsyncSession,
    *,
    resolver_spec: dict[str, Any],
    input_field: str,
    raw_value: Any,
) -> list[Any]:
    model_name = str(resolver_spec.get("model") or "").strip()
    if not model_name:
        return []

    model = await _load_semantic_model_by_name(db, model_name)
    definition = await _resolve_model_definition(db, model, seen=set())
    sources = definition.get("sources") or []
    if len(sources) != 1 or definition.get("joins"):
        raise SemanticDefinitionError(f"解析模型 {model_name} 必须是单源维度模型")

    table_name = str(sources[0]["table"])
    alias = str(sources[0]["alias"])
    source_column = _resolve_resolver_column(definition, input_field, alias)
    output_field = str(resolver_spec.get("output_field") or resolver_spec.get("primary_key") or "").strip()
    output_column = _resolve_resolver_column(definition, output_field, alias)
    values = _normalize_filter_values(raw_value)
    if not values:
        return []

    clauses: list[str] = []
    params: dict[str, Any] = {}
    for index, item in enumerate(values):
        pname = f"v{index}"
        if isinstance(item, str) and input_field != output_field:
            clauses.append(f"{source_column} ILIKE :{pname}")
            params[pname] = f"%{item}%"
        else:
            clauses.append(f"{source_column} = :{pname}")
            params[pname] = item

    sql = (
        f"SELECT DISTINCT {output_column} AS resolved_value "
        f"FROM {quote_identifier(table_name)} AS {quote_identifier(alias)} "
        f"WHERE {' OR '.join(clauses)}"
    )
    result = await db.execute(text(sql), params)
    resolved_values: list[Any] = []
    for row in result.mappings().all():
        value = row.get("resolved_value")
        if value is not None and value not in resolved_values:
            resolved_values.append(value)
    return resolved_values


def _resolve_resolver_column(definition: dict[str, Any], field_name: str, default_alias: str) -> str:
    for item in definition.get("dimensions", []):
        if str(item.get("name") or "") != field_name:
            continue
        expr = item.get("expr") or item.get("expression")
        if expr:
            return str(expr)
        column = str(item.get("column") or field_name)
        source = str(item.get("source") or default_alias)
        return f"{quote_identifier(source)}.{quote_identifier(column)}"

    return f"{quote_identifier(default_alias)}.{quote_identifier(field_name)}"


def _normalize_filter_values(value: Any) -> list[Any]:
    if isinstance(value, (list, tuple)):
        values = list(value)
    else:
        values = [value]

    normalized: list[Any] = []
    for item in values:
        if item is None:
            continue
        if item not in normalized:
            normalized.append(item)
    return normalized


def _append_resolved_filter(
    filters: list[dict[str, Any]],
    resolved_filter_map: dict[str, list[Any]],
    field: str,
    value: Any,
) -> None:
    values = _normalize_filter_values(value)
    if not values:
        return

    if len(values) == 1:
        filters.append({"field": field, "op": "eq", "value": values[0]})
    else:
        filters.append({"field": field, "op": "in", "value": values})

    existing = resolved_filter_map.setdefault(field, [])
    for item in values:
        if item not in existing:
            existing.append(item)
