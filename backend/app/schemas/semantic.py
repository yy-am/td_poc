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
    entity_filters: dict[str, Any] = Field(default_factory=dict)
    resolved_filters: dict[str, Any] = Field(default_factory=dict)
    grain: Optional[str] = None
    limit: int = 100


class TdaMqlHeader(BaseModel):
    reasoning: Optional[str] = None


class TdaMqlSelectItem(BaseModel):
    metric: str
    alias: Optional[str] = None


class TdaMqlFilter(BaseModel):
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
    values: list[Any] = Field(default_factory=list)


class TdaMqlOrder(BaseModel):
    field: str
    direction: Literal["asc", "desc"] = "asc"


class TdaMqlTimeContext(BaseModel):
    grain: Optional[str] = None
    range: Optional[str] = None
    compare: Optional[str] = None
    role: Optional[str] = None


class TdaMqlAnalysisMode(BaseModel):
    type: Optional[str] = None
    attribution: bool = False
    top_k: int = 3


class TdaMqlDrilldown(BaseModel):
    enabled: bool = False
    target: Optional[str] = None
    detail_fields: list[str] = Field(default_factory=list)
    limit: Optional[int] = None


class TdaMqlRequest(BaseModel):
    header: Optional[TdaMqlHeader] = None
    model_name: str
    select: list[TdaMqlSelectItem] = Field(default_factory=list)
    group_by: list[str] = Field(default_factory=list)
    entity_filters: dict[str, Any] = Field(default_factory=dict)
    resolved_filters: dict[str, Any] = Field(default_factory=dict)
    filters: list[TdaMqlFilter] = Field(default_factory=list)
    time_context: Optional[TdaMqlTimeContext] = None
    analysis_mode: Optional[TdaMqlAnalysisMode] = None
    drilldown: Optional[TdaMqlDrilldown] = None
    order: list[TdaMqlOrder] = Field(default_factory=list)
    limit: int = 100


class TdaMqlCompilationResponse(BaseModel):
    model_name: str
    semantic_query: dict[str, Any]
    metric_aliases: dict[str, str] = Field(default_factory=dict)
    unsupported_features: list[str] = Field(default_factory=list)
    relationship_graph: list[dict[str, Any]] = Field(default_factory=list)
    metric_lineage: list[dict[str, Any]] = Field(default_factory=list)
    detail_fields: list[dict[str, Any]] = Field(default_factory=list)
    query_hints: dict[str, Any] = Field(default_factory=dict)


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
    resolved_filters: dict[str, list[Any]] = Field(default_factory=dict)
    resolution_log: list[str] = Field(default_factory=list)
    semantic_kind: Optional[str] = None
    semantic_domain: Optional[str] = None
    semantic_grain: Optional[str] = None


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
    has_yaml_definition: bool = False
    semantic_kind: Optional[str] = None
    semantic_domain: Optional[str] = None
    semantic_grain: Optional[str] = None
    entry_enabled: bool = False
    source_count: int = 0
    join_count: int = 0
    business_terms: list[str] = Field(default_factory=list)
    intent_aliases: list[str] = Field(default_factory=list)
    analysis_patterns: list[str] = Field(default_factory=list)
    evidence_requirements: list[str] = Field(default_factory=list)
    fallback_policy: str = "fallback_to_sql"
    dimensions: list[str] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=list)
    entities: dict[str, Any] = Field(default_factory=dict)
    time: dict[str, Any] = Field(default_factory=dict)
    supports_entity_resolution: bool = False
    relationship_graph: list[dict[str, Any]] = Field(default_factory=list)
    metric_lineage: list[dict[str, Any]] = Field(default_factory=list)
    detail_fields: list[dict[str, Any]] = Field(default_factory=list)
    materialization_policy: dict[str, Any] = Field(default_factory=dict)
    query_hints: dict[str, Any] = Field(default_factory=dict)

    class Config:
        from_attributes = True
