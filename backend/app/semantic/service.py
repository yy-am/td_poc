"""Semantic query execution service."""

from __future__ import annotations

from typing import Any

from sqlalchemy import inspect, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.semantic import SysSemanticModel
from app.schemas.semantic import SemanticQueryRequest, SemanticQueryResponse

from .compiler import (
    SemanticDefinitionError,
    compile_semantic_query,
    load_semantic_definition,
    normalize_definition,
)


async def semantic_query(
    model_name: str | None = None,
    model_id: int | None = None,
    dimensions: list[str] | None = None,
    metrics: list[str] | None = None,
    filters: list[dict[str, Any]] | None = None,
    order: list[dict[str, Any]] | None = None,
    limit: int = 100,
    db: AsyncSession | None = None,
) -> dict[str, Any]:
    """Execute a semantic query from YAML or a fallback physical-table definition."""

    request = SemanticQueryRequest(
        model_name=model_name,
        model_id=model_id,
        dimensions=dimensions or [],
        metrics=metrics or [],
        filters=filters or [],
        order=order or [],
        limit=limit,
    )

    if db is None:
        async with AsyncSessionLocal() as session:
            return await _semantic_query_with_session(session, request)
    return await _semantic_query_with_session(db, request)


async def _semantic_query_with_session(db: AsyncSession, request: SemanticQueryRequest) -> dict[str, Any]:
    model = await _load_semantic_model(db, request)
    definition = await _load_semantic_definition(db, model)

    selected_dimensions = list(request.dimensions)
    selected_metrics = list(request.metrics)
    warnings: list[str] = []
    if not selected_dimensions and not selected_metrics:
        if definition.get("metrics"):
            selected_metrics = [definition["metrics"][0]["name"]]
            warnings.append(f"未指定指标，默认使用 {selected_metrics[0]}")
        if definition.get("dimensions"):
            selected_dimensions = [definition["dimensions"][0]["name"]]
            warnings.append(f"未指定维度，默认使用 {selected_dimensions[0]}")
        if not selected_dimensions and not selected_metrics:
            raise SemanticDefinitionError("semantic_query 至少需要一个 dimension 或 metric")

    compiled = compile_semantic_query(
        definition=definition,
        model_name=model.name,
        model_label=model.label,
        request_dimensions=selected_dimensions,
        request_metrics=selected_metrics,
        filters=[item.model_dump() for item in request.filters],
        order=[item.model_dump() for item in request.order],
        limit=request.limit,
    )
    compiled.warnings.extend(warnings)

    result = await db.execute(text(compiled.sql), compiled.params)
    rows = [dict(row) for row in result.mappings().all()]
    columns = list(result.keys())

    response = SemanticQueryResponse(
        model_id=model.id,
        model_name=model.name,
        model_label=model.label,
        source_table=model.source_table,
        sql=compiled.sql,
        columns=columns,
        rows=rows,
        row_count=len(rows),
        selected_dimensions=compiled.selected_dimensions,
        selected_metrics=compiled.selected_metrics,
        warnings=compiled.warnings,
    )
    return response.model_dump()


async def _load_semantic_model(db: AsyncSession, request: SemanticQueryRequest) -> SysSemanticModel:
    if request.model_id is None and not request.model_name:
        raise SemanticDefinitionError("semantic_query 需要 model_id 或 model_name")

    stmt = select(SysSemanticModel)
    if request.model_id is not None:
        stmt = stmt.where(SysSemanticModel.id == request.model_id)
    else:
        stmt = stmt.where(SysSemanticModel.name == request.model_name)

    result = await db.execute(stmt)
    model = result.scalar_one_or_none()
    if model is None:
        raise SemanticDefinitionError("语义模型不存在")
    if model.status != "active":
        raise SemanticDefinitionError(f"语义模型 {model.name} 当前不可用")
    return model


async def _load_semantic_definition(db: AsyncSession, model: SysSemanticModel) -> dict[str, Any]:
    if model.yaml_definition and model.yaml_definition.strip():
        definition = load_semantic_definition(model.yaml_definition)
        return normalize_definition(
            definition,
            fallback_name=model.name,
            fallback_label=model.label,
            fallback_table=model.source_table,
        )
    return await _build_fallback_definition(db, model)


async def _build_fallback_definition(db: AsyncSession, model: SysSemanticModel) -> dict[str, Any]:
    conn = await db.connection()

    def read_columns(sync_conn):
        inspector = inspect(sync_conn)
        if model.source_table not in inspector.get_table_names():
            raise SemanticDefinitionError(f"物理表不存在: {model.source_table}")
        return inspector.get_columns(model.source_table)

    columns = await conn.run_sync(read_columns)

    dimensions: list[dict[str, Any]] = []
    metrics: list[dict[str, Any]] = []
    for column in columns:
        name = column["name"]
        data_type = str(column.get("type", "")).lower()
        is_numeric = any(token in data_type for token in ("int", "numeric", "decimal", "float", "double", "real", "number"))
        is_temporal = any(token in data_type for token in ("date", "time", "timestamp"))
        is_key_like = name.endswith("_id") or name.endswith("id")

        if is_numeric and not is_key_like:
            metrics.append({"name": name, "label": name, "column": name, "agg": "sum"})
        else:
            dimensions.append({"name": name, "label": name, "column": name})

        if is_temporal and not any(item["name"] == name for item in dimensions):
            dimensions.append({"name": name, "label": name, "column": name})

    return normalize_definition(
        {
            "name": model.name,
            "label": model.label,
            "table": model.source_table,
            "description": model.description or "",
            "dimensions": dimensions,
            "metrics": metrics,
            "default_limit": 100,
        },
        fallback_name=model.name,
        fallback_label=model.label,
        fallback_table=model.source_table,
    )
