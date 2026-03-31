"""Pydantic schemas"""
from pydantic import BaseModel, Field
from typing import Optional, Any
from datetime import datetime


class ChatMessage(BaseModel):
    content: str
    session_id: Optional[str] = None


class AgentStep(BaseModel):
    type: str = Field(description="步骤类型: thinking/action/observation/answer/chart/table/error/status")
    step_number: int = 0
    content: str = ""
    metadata: Optional[dict[str, Any]] = None
    timestamp: str = ""
    is_final: bool = False


class SessionCreate(BaseModel):
    title: Optional[str] = None
    user_id: str = "default"


class SessionUpdate(BaseModel):
    title: Optional[str] = None
    status: Optional[str] = None


class SessionResponse(BaseModel):
    id: int
    session_id: str
    title: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ConversationMessageResponse(BaseModel):
    id: int
    session_id: str
    role: str
    content: str
    message_type: str
    metadata: Optional[dict[str, Any]] = None
    created_at: datetime

    class Config:
        from_attributes = True


class SemanticModelResponse(BaseModel):
    id: int
    name: str
    label: str
    description: Optional[str]
    source_table: str
    model_type: str
    status: str
    yaml_definition: Optional[str] = None
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


class MetricResponse(BaseModel):
    name: str
    label: str
    expression: str
    format: Optional[str] = None


class DimensionResponse(BaseModel):
    name: str
    label: str
    column: str
    type: str


class TableSchemaResponse(BaseModel):
    table_name: str
    columns: list[dict[str, str]]
    row_count: int = 0


class PreferenceUpdate(BaseModel):
    preference_type: str
    preference_key: str
    preference_value: str


class KnowledgeSearchRequest(BaseModel):
    query: str
    top_k: int = 5
