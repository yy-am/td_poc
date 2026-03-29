"""Schemas for semantic query support."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class SemanticQueryFilter(BaseModel):
    field: str
    op: Literal[
        "eq",
        "ne",
        "gt",
        "gte",
        "lt",
        "lte",
        "in",
        "not_in",
        "like",
        "ilike",
        "contains",
        "startswith",
        "endswith",
        "between",
        "is_null",
        "not_null",
    ] = "eq"
    value: Any = None


class SemanticQueryOrder(BaseModel):
    field: str
    direction: Literal["asc", "desc"] = "asc"


class SemanticQueryRequest(BaseModel):
    model_name: Optional[str] = None
    model_id: Optional[int] = None
    dimensions: list[str] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=list)
    filters: list[SemanticQueryFilter] = Field(default_factory=list)
    order: list[SemanticQueryOrder] = Field(default_factory=list)
    limit: int = 100


class SemanticQueryResponse(BaseModel):
    model_id: int
    model_name: str
    model_label: str
    source_table: str
    sql: str
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    selected_dimensions: list[str]
    selected_metrics: list[str]
    warnings: list[str] = Field(default_factory=list)


class SemanticDefinitionResponse(BaseModel):
    name: str
    label: str
    table: str
    description: Optional[str] = None
    dimensions: list[dict[str, Any]] = Field(default_factory=list)
    metrics: list[dict[str, Any]] = Field(default_factory=list)
    default_limit: Optional[int] = None


class SemanticModelSummary(BaseModel):
    id: int
    name: str
    label: str
    description: Optional[str]
    source_table: str
    model_type: str
    status: str
    updated_at: datetime

    class Config:
        from_attributes = True
