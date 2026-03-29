"""Semantic query execution service."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select, text
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
    """Execute a semantic query from the registered YAML definition."""

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
    definition = load_semantic_definition(model.yaml_definition)
    normalized = normalize_definition(
        definition,
        fallback_name=model.name,
        fallback_label=model.label,
        fallback_table=model.source_table,
    )
    compiled = compile_semantic_query(
        definition=normalized,
        model_name=model.name,
        model_label=model.label,
        request_dimensions=request.dimensions,
        request_metrics=request.metrics,
        filters=[item.model_dump() for item in request.filters],
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
