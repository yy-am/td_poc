"""Semantic model management API."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.semantic import SysSemanticModel
from app.schemas.chat import SemanticModelResponse
from app.schemas.semantic import SemanticQueryRequest
from app.semantic import semantic_query as execute_semantic_query
from app.semantic.compiler import SemanticDefinitionError

router = APIRouter()


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
    result = await db.execute(select(SysSemanticModel).order_by(SysSemanticModel.updated_at.desc(), SysSemanticModel.id.desc()))
    models = result.scalars().all()
    return [SemanticModelResponse.model_validate(model) for model in models]


@router.post("/models")
async def create_model(body: SemanticModelCreate, db: AsyncSession = Depends(get_db)):
    model = SysSemanticModel(**body.model_dump())
    db.add(model)
    await db.commit()
    await db.refresh(model)
    return SemanticModelResponse.model_validate(model)


@router.get("/models/{model_id}")
async def get_model(model_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SysSemanticModel).where(SysSemanticModel.id == model_id))
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=404, detail="模型不存在")
    return model


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
    return SemanticModelResponse.model_validate(model)


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
    result = await db.execute(select(SysSemanticModel).order_by(SysSemanticModel.model_type, SysSemanticModel.id))
    models = result.scalars().all()

    catalog = {"physical": [], "semantic": [], "metric": []}
    for model in models:
        entry = SemanticModelResponse.model_validate(model).model_dump()
        catalog.setdefault(model.model_type, catalog["physical"]).append(entry)

    table_stats: dict[str, int] = {}
    for model in models:
        try:
            count_result = await db.execute(text(f'SELECT COUNT(*) FROM "{model.source_table}"'))
            table_stats[model.source_table] = int(count_result.scalar() or 0)
        except Exception:
            table_stats[model.source_table] = 0

    return {"models": catalog, "table_stats": table_stats}


@router.post("/query")
async def semantic_query(body: SemanticQueryRequest, db: AsyncSession = Depends(get_db)):
    try:
        return await execute_semantic_query(
            model_name=body.model_name,
            model_id=body.model_id,
            dimensions=body.dimensions,
            metrics=body.metrics,
            filters=[item.model_dump() for item in body.filters],
            order=[item.model_dump() for item in body.order],
            limit=body.limit,
            db=db,
        )
    except SemanticDefinitionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
