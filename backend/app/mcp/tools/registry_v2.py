"""Tool registry used by the agent."""

from __future__ import annotations

import re

from sqlalchemy import inspect

from app.database import AsyncSessionLocal
from app.mcp.tools.sql_executor import chart_generator, knowledge_search, sql_executor
from app.semantic.service_v2 import semantic_query

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


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "sql_executor",
            "description": "执行只读 SQL 查询。只允许 SELECT。用于复杂自定义查询、统计和明细分析。",
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
            "description": "查询数据库元数据。不传 table_name 时返回全部表；传入 table_name 时返回该表字段信息。",
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
            "name": "semantic_query",
            "description": "通过语义模型查询数据。优先用于指标、维度、筛选、排序和限制行数的标准分析场景。",
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
    "semantic_query": semantic_query,
    "chart_generator": chart_generator,
    "knowledge_search": knowledge_search,
}
