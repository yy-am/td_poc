"""语义模型管理 API."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.semantic import SysSemanticModel
from app.schemas.chat import SemanticModelResponse
from app.schemas.semantic import (
    SemanticModelSummary,
    SemanticQueryRequest,
    TdaMqlCompilationResponse,
    TdaMqlRequest,
)
from app.semantic.catalog import extract_semantic_metadata
from app.semantic.compiler_v2 import SemanticDefinitionError
from app.semantic.mql import compile_tda_mql_request, execute_tda_mql_request
from app.semantic.service_v3 import semantic_query as execute_semantic_query

router = APIRouter()


def _build_semantic_model_payload(model: SysSemanticModel) -> dict:
    payload = {
        "id": model.id,
        "name": model.name,
        "label": model.label,
        "description": model.description,
        "source_table": model.source_table,
        "model_type": model.model_type,
        "status": model.status,
        "yaml_definition": model.yaml_definition,
        "updated_at": model.updated_at,
    }
    payload.update(
        extract_semantic_metadata(
            name=model.name,
            label=model.label,
            description=model.description or "",
            source_table=model.source_table,
            model_type=model.model_type,
            yaml_definition=model.yaml_definition,
            status=model.status,
        )
    )
    return payload


class SemanticModelCreate(BaseModel):
    name: str
    label: str
    description: Optional[str] = None
    source_table: str
    model_type: str = "physical"
    yaml_definition: Optional[str] = None


class SemanticModelUpdate(BaseModel):
    label: Optional[str] = None
    description: Optional[str] = None
    yaml_definition: Optional[str] = None
    status: Optional[str] = None


@router.get("/models")
async def list_models(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SysSemanticModel).order_by(SysSemanticModel.id))
    models = result.scalars().all()
    return [SemanticModelSummary.model_validate(_build_semantic_model_payload(model)) for model in models]


@router.post("/models")
async def create_model(body: SemanticModelCreate, db: AsyncSession = Depends(get_db)):
    model = SysSemanticModel(**body.model_dump())
    db.add(model)
    await db.commit()
    await db.refresh(model)
    return SemanticModelResponse.model_validate(_build_semantic_model_payload(model))


@router.get("/models/{model_id}")
async def get_model(model_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SysSemanticModel).where(SysSemanticModel.id == model_id))
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=404, detail="模型不存在")
    return SemanticModelResponse.model_validate(_build_semantic_model_payload(model))


@router.put("/models/{model_id}")
async def update_model(model_id: int, body: SemanticModelUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SysSemanticModel).where(SysSemanticModel.id == model_id))
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=404, detail="模型不存在")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(model, key, value)
    await db.commit()
    await db.refresh(model)
    return SemanticModelResponse.model_validate(_build_semantic_model_payload(model))


@router.delete("/models/{model_id}")
async def delete_model(model_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SysSemanticModel).where(SysSemanticModel.id == model_id))
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=404, detail="模型不存在")
    await db.delete(model)
    await db.commit()
    return {"status": "deleted"}


@router.get("/catalog")
async def get_catalog(db: AsyncSession = Depends(get_db)):
    """返回语义目录，兼容旧的按 model_type 分组，同时补充按 semantic_kind 分组。"""

    result = await db.execute(select(SysSemanticModel).order_by(SysSemanticModel.model_type, SysSemanticModel.id))
    models = result.scalars().all()

    catalog_by_type = {"physical": [], "semantic": [], "metric": []}
    catalog_by_kind = {"entity_dimension": [], "atomic_fact": [], "composite_analysis": []}
    for model in models:
        entry = SemanticModelResponse.model_validate(_build_semantic_model_payload(model)).model_dump()
        catalog_by_type.setdefault(model.model_type, catalog_by_type["physical"]).append(entry)
        semantic_kind = str(entry.get("semantic_kind") or "")
        if semantic_kind in catalog_by_kind:
            catalog_by_kind[semantic_kind].append(entry)

    table_stats: dict[str, int] = {}
    for model in models:
        try:
            count_result = await db.execute(text(f'SELECT COUNT(*) FROM "{model.source_table}"'))
            table_stats[model.source_table] = int(count_result.scalar() or 0)
        except Exception:
            table_stats[model.source_table] = 0

    return {
        "models": catalog_by_type,
        "catalog_by_type": catalog_by_type,
        "catalog_by_kind": catalog_by_kind,
        "table_stats": table_stats,
    }


@router.post("/query")
async def query_semantic_model(body: SemanticQueryRequest, db: AsyncSession = Depends(get_db)):
    try:
        return await execute_semantic_query(
            model_name=body.model_name,
            model_id=body.model_id,
            dimensions=body.dimensions,
            metrics=body.metrics,
            filters=[item.model_dump() for item in body.filters],
            order=[item.model_dump() for item in body.order],
            entity_filters=body.entity_filters,
            resolved_filters=body.resolved_filters,
            grain=body.grain,
            limit=body.limit,
            db=db,
        )
    except SemanticDefinitionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/mql/validate", response_model=TdaMqlCompilationResponse)
async def validate_tda_mql(body: TdaMqlRequest, db: AsyncSession = Depends(get_db)):
    try:
        compiled = await compile_tda_mql_request(body, db)
        return TdaMqlCompilationResponse.model_validate(compiled)
    except SemanticDefinitionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/mql/query")
async def query_by_tda_mql(body: TdaMqlRequest, db: AsyncSession = Depends(get_db)):
    try:
        return await execute_tda_mql_request(body, db)
    except SemanticDefinitionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
