"""Tool registry used by the agent."""

from __future__ import annotations

import re

from sqlalchemy import inspect

from app.database import AsyncSessionLocal
from app.mcp.tools.sql_executor import chart_generator, knowledge_search, sql_executor
from app.schemas.semantic import TdaMqlRequest
from app.semantic.mql import execute_tda_mql_request
from app.semantic.service_v3 import semantic_query

VALID_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


async def metadata_query(table_name: str | None = None) -> dict:
    try:
        async with AsyncSessionLocal() as session:
            conn = await session.connection()
            if table_name:
                if not VALID_IDENTIFIER.fullmatch(table_name):
                    return {"error": "invalid table name"}

                def read_columns(sync_conn):
                    inspector = inspect(sync_conn)
                    table_names = inspector.get_table_names()
                    if table_name not in table_names:
                        return None
                    return inspector.get_columns(table_name)

                raw_columns = await conn.run_sync(read_columns)
                if raw_columns is None:
                    return {"error": f"table not found: {table_name}"}

                columns = []
                for column in raw_columns:
                    columns.append(
                        {
                            "column_name": column["name"],
                            "data_type": str(column["type"]),
                            "nullable": "YES" if column.get("nullable", True) else "NO",
                            "comment": column.get("comment") or "",
                        }
                    )
                return {"table_name": table_name, "columns": columns}

            tables = await conn.run_sync(lambda sync_conn: sorted(inspect(sync_conn).get_table_names()))
            return {"tables": tables, "count": len(tables)}
    except Exception as exc:
        return {"error": f"metadata query failed: {exc}"}


async def mql_query(
    model_name: str,
    select: list[dict] | None = None,
    group_by: list[str] | None = None,
    entity_filters: dict | None = None,
    resolved_filters: dict | None = None,
    filters: list[dict] | None = None,
    time_context: dict | None = None,
    analysis_mode: dict | None = None,
    drilldown: dict | None = None,
    order: list[dict] | None = None,
    limit: int = 100,
) -> dict:
    try:
        request = TdaMqlRequest(
            model_name=model_name,
            select=select or [],
            group_by=group_by or [],
            entity_filters=entity_filters or {},
            resolved_filters=resolved_filters or {},
            filters=filters or [],
            time_context=time_context,
            analysis_mode=analysis_mode,
            drilldown=drilldown,
            order=order or [],
            limit=limit,
        )
        async with AsyncSessionLocal() as session:
            return await execute_tda_mql_request(request, session)
    except Exception as exc:
        return {"error": f"mql query failed: {exc}"}


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "sql_executor",
            "description": "执行只读 SQL 查询，只允许 SELECT，用于复杂定制查询、明细穿透和兜底分析。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "SQL SELECT 查询语句"},
                    "limit": {"type": "integer", "description": "最大返回行数", "default": 1000},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "metadata_query",
            "description": "查询数据库元数据。不传 table_name 时返回全部表，传入 table_name 时返回该表字段信息。",
            "parameters": {
                "type": "object",
                "properties": {
                    "table_name": {"type": "string", "description": "可选，指定表名"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mql_query",
            "description": "通过 TDA-MQL 执行显式语义查询。仅在语义绑定明确且要求走 MQL 主路径时使用，不做隐式 SQL 降级。",
            "parameters": {
                "type": "object",
                "properties": {
                    "model_name": {"type": "string", "description": "目标语义模型名称"},
                    "select": {
                        "type": "array",
                        "description": "指标选择列表",
                        "items": {
                            "type": "object",
                            "properties": {
                                "metric": {"type": "string"},
                                "alias": {"type": "string"},
                            },
                            "required": ["metric"],
                        },
                    },
                    "group_by": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "维度分组列表",
                    },
                    "entity_filters": {
                        "type": "object",
                        "description": "业务实体过滤条件",
                    },
                    "resolved_filters": {
                        "type": "object",
                        "description": "已解析的底层键过滤条件",
                    },
                    "filters": {
                        "type": "array",
                        "description": "附加过滤条件列表",
                        "items": {
                            "type": "object",
                            "properties": {
                                "field": {"type": "string"},
                                "op": {"type": "string"},
                                "value": {},
                                "values": {"type": "array", "items": {}},
                            },
                            "required": ["field"],
                        },
                    },
                    "time_context": {
                        "type": "object",
                        "description": "时间语义，例如 grain/range/role",
                    },
                    "analysis_mode": {
                        "type": "object",
                        "description": "分析模式，例如 type / attribution / top_k",
                    },
                    "drilldown": {
                        "type": "object",
                        "description": "下钻配置",
                    },
                    "order": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "field": {"type": "string"},
                                "direction": {"type": "string"},
                            },
                            "required": ["field"],
                        },
                    },
                    "limit": {"type": "integer", "description": "最大返回行数", "default": 100},
                },
                "required": ["model_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "semantic_query",
            "description": "通过语义模型查询数据，优先用于语义绑定明确的指标、维度、实体过滤和分析场景。",
            "parameters": {
                "type": "object",
                "properties": {
                    "model_name": {"type": "string", "description": "语义模型名称"},
                    "model_id": {"type": "integer", "description": "语义模型 ID"},
                    "dimensions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "维度字段列表",
                    },
                    "metrics": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "指标字段列表",
                    },
                    "filters": {
                        "type": "array",
                        "description": "过滤条件列表",
                        "items": {
                            "type": "object",
                            "properties": {
                                "field": {"type": "string"},
                                "op": {"type": "string"},
                                "value": {},
                            },
                            "required": ["field", "op"],
                        },
                    },
                    "order": {
                        "type": "array",
                        "description": "排序条件列表",
                        "items": {
                            "type": "object",
                            "properties": {
                                "field": {"type": "string"},
                                "direction": {"type": "string"},
                            },
                            "required": ["field"],
                        },
                    },
                    "entity_filters": {
                        "type": "object",
                        "description": "待解析的业务实体过滤条件，例如 enterprise_name、industry_name",
                    },
                    "resolved_filters": {
                        "type": "object",
                        "description": "已解析到底层键值的过滤条件，例如 taxpayer_id、industry_code",
                    },
                    "grain": {
                        "type": "string",
                        "description": "查询粒度，例如 month、quarter、year、enterprise",
                    },
                    "limit": {"type": "integer", "description": "最大返回行数", "default": 100},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "chart_generator",
            "description": "基于查询结果生成 ECharts 配置。",
            "parameters": {
                "type": "object",
                "properties": {
                    "data": {
                        "type": "object",
                        "description": "查询结果，格式为 {columns: [...], rows: [...]}",
                    },
                    "chart_type": {
                        "type": "string",
                        "enum": ["bar", "line", "pie", "scatter"],
                        "description": "图表类型",
                        "default": "bar",
                    },
                    "title": {"type": "string", "description": "图表标题"},
                    "description": {"type": "string", "description": "图表说明"},
                },
                "required": ["data", "chart_type", "title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "knowledge_search",
            "description": "检索税务、会计和对账知识，用于解释规则和差异原因。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                    "top_k": {"type": "integer", "description": "返回条数", "default": 5},
                },
                "required": ["query"],
            },
        },
    },
]


TOOL_FUNCTIONS = {
    "sql_executor": sql_executor,
    "metadata_query": metadata_query,
    "mql_query": mql_query,
    "semantic_query": semantic_query,
    "chart_generator": chart_generator,
    "knowledge_search": knowledge_search,
}
