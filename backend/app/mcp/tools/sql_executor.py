"""MCP Tools — 数据库交互工具集

这些工具以函数形式注册，供 ReAct Agent 通过 LLM function calling 调用。
同时也可以通过 MCP 协议对外暴露。
"""
import json
from typing import Optional
from sqlalchemy import text
from app.database import AsyncSessionLocal


# ========== Tool: SQL执行器 ==========
async def sql_executor(query: str, limit: int = 1000) -> dict:
    """执行只读SQL查询。仅允许SELECT语句。

    Args:
        query: SQL查询语句（必须是SELECT）
        limit: 最大返回行数，默认1000

    Returns:
        {"columns": [...], "rows": [...], "row_count": N}
    """
    query = query.strip()
    if not query.upper().startswith("SELECT"):
        return {"error": "安全限制: 仅允许SELECT查询语句"}

    # 自动添加LIMIT
    if "LIMIT" not in query.upper():
        query = f"{query} LIMIT {limit}"

    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(text(query))
            columns = list(result.keys())
            rows = []
            for row in result.fetchall():
                rows.append({col: _serialize(val) for col, val in zip(columns, row)})
            return {
                "columns": columns,
                "rows": rows,
                "row_count": len(rows),
                "sql": query,
            }
    except Exception as e:
        return {"error": f"SQL执行失败: {str(e)}", "sql": query}


# ========== Tool: 元数据查询 ==========
async def metadata_query(table_name: Optional[str] = None) -> dict:
    """查询数据库元数据。

    Args:
        table_name: 表名。如果为空则返回所有表的列表。

    Returns:
        表列表或指定表的字段信息
    """
    try:
        async with AsyncSessionLocal() as session:
            if table_name:
                result = await session.execute(text("""
                    SELECT column_name, data_type, is_nullable,
                           col_description((table_schema||'.'||table_name)::regclass, ordinal_position) as comment
                    FROM information_schema.columns
                    WHERE table_name = :table_name AND table_schema = 'public'
                    ORDER BY ordinal_position
                """), {"table_name": table_name})
                columns = []
                for row in result:
                    columns.append({
                        "column_name": row[0],
                        "data_type": row[1],
                        "nullable": row[2],
                        "comment": row[3] or "",
                    })
                return {"table_name": table_name, "columns": columns}
            else:
                result = await session.execute(text("""
                    SELECT table_name FROM information_schema.tables
                    WHERE table_schema = 'public' ORDER BY table_name
                """))
                tables = [row[0] for row in result]
                return {"tables": tables, "count": len(tables)}
    except Exception as e:
        return {"error": f"元数据查询失败: {str(e)}"}


# ========== Tool: 图表配置生成 ==========
async def chart_generator(
    data: dict,
    chart_type: str = "bar",
    title: str = "",
    description: str = "",
) -> dict:
    """根据查询结果数据生成 ECharts 配置。

    Args:
        data: 查询结果 {"columns": [...], "rows": [...]}
        chart_type: 图表类型 bar/line/pie/scatter
        title: 图表标题
        description: 图表描述

    Returns:
        ECharts option 配置对象
    """
    columns = data.get("columns", [])
    rows = data.get("rows", [])

    if not rows or not columns:
        return {"error": "数据为空，无法生成图表"}

    # 第一列作为分类轴，其余列作为数值系列
    x_field = columns[0]
    x_data = [str(row.get(x_field, "")) for row in rows]
    series = []

    for col in columns[1:]:
        values = []
        for row in rows:
            val = row.get(col, 0)
            try:
                values.append(float(val) if val is not None else 0)
            except (TypeError, ValueError):
                values.append(0)
        series.append({
            "name": col,
            "type": chart_type if chart_type != "pie" else "bar",
            "data": values,
        })

    if chart_type == "pie" and len(columns) >= 2:
        pie_data = []
        value_field = columns[1]
        for row in rows:
            pie_data.append({
                "name": str(row.get(x_field, "")),
                "value": float(row.get(value_field, 0) or 0),
            })
        option = {
            "title": {"text": title, "left": "center"},
            "tooltip": {"trigger": "item"},
            "legend": {"orient": "vertical", "left": "left"},
            "series": [{"type": "pie", "radius": "50%", "data": pie_data}],
        }
    else:
        option = {
            "title": {"text": title, "left": "center"},
            "tooltip": {"trigger": "axis"},
            "legend": {"data": [s["name"] for s in series], "top": 30},
            "grid": {"left": "3%", "right": "4%", "bottom": "3%", "containLabel": True},
            "xAxis": {"type": "category", "data": x_data},
            "yAxis": {"type": "value"},
            "series": series,
        }

    return {"chart_config": option, "chart_type": chart_type, "description": description}


# ========== Tool: 知识库搜索（占位，Phase 4实现） ==========
async def knowledge_search(query: str, top_k: int = 5) -> list[dict]:
    """搜索知识库中的税务法规和会计准则。

    Args:
        query: 搜索关键词
        top_k: 返回条数

    Returns:
        相关文档片段列表
    """
    # Phase 4 接入ChromaDB后实现实际搜索
    # 目前返回内置的常用税务知识
    knowledge_base = [
        {"title": "增值税收入确认", "content": "增值税收入确认时点以发票开具或收讫销售款项为准，与会计收入确认时点可能不同。常见差异包括：预收款项、分期收款、委托代销等场景。"},
        {"title": "视同销售", "content": "《增值税暂行条例实施细则》规定，将自产、委托加工的货物用于非应税项目、集体福利、个人消费、投资、分配、赠送等，视同销售货物。需要在增值税申报中计入销售额，但会计上可能不确认收入。"},
        {"title": "企业所得税纳税调整", "content": "企业所得税汇算清缴时常见调整项目：1)职工福利费超限(不超过工资14%)；2)业务招待费(60%且不超过营收0.5%)；3)广告费(不超过营收15%)；4)折旧方法差异；5)坏账准备（税法按实际发生扣除）；6)罚款支出（不可税前扣除）。"},
        {"title": "增值税税负率预警", "content": "税务机关通过行业平均税负率进行风险监控。增值税税负率=应纳增值税÷应税销售收入×100%。低于行业平均值60%以上会触发预警。各行业参考：制造业3-5%、批发零售1-2%、服务业5-6%。"},
        {"title": "暂时性差异与递延所得税", "content": "暂时性差异指资产或负债的账面价值与计税基础之间的差额，未来期间会转回。常见来源：折旧方法差异、坏账准备计提、资产减值准备等。暂时性差异×所得税税率=递延所得税资产/负债。"},
        {"title": "税会差异分类", "content": "税会差异分为永久性差异和暂时性差异。永久性差异如：罚款支出、超标招待费、免税收入等，不会在未来转回。暂时性差异如：折旧差异、坏账准备、资产减值等，会在未来期间转回。"},
    ]

    # 简单关键词匹配
    results = []
    query_lower = query.lower()
    for doc in knowledge_base:
        score = sum(1 for word in query_lower if word in doc["title"].lower() or word in doc["content"].lower())
        if score > 0 or len(results) < top_k:
            results.append({"title": doc["title"], "content": doc["content"], "score": score})

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]


# ========== 工具注册表 — 供 Agent 使用 ==========
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "sql_executor",
            "description": "执行只读SQL查询。仅允许SELECT语句。用于查询PostgreSQL数据库中的税务和会计数据。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "SQL SELECT查询语句"},
                    "limit": {"type": "integer", "description": "最大返回行数，默认1000", "default": 1000},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "metadata_query",
            "description": "查询数据库元数据。不传table_name返回所有表列表，传入table_name返回该表的字段信息（字段名、类型、注释）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "table_name": {"type": "string", "description": "表名，留空则返回全部表列表"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "chart_generator",
            "description": "根据查询结果数据生成ECharts图表配置。前端会自动渲染此配置为可视化图表。",
            "parameters": {
                "type": "object",
                "properties": {
                    "data": {
                        "type": "object",
                        "description": "查询结果数据，格式: {columns: [...], rows: [{...}, ...]}",
                        "properties": {
                            "columns": {"type": "array", "items": {"type": "string"}},
                            "rows": {"type": "array", "items": {"type": "object"}},
                        },
                    },
                    "chart_type": {"type": "string", "enum": ["bar", "line", "pie", "scatter"], "description": "图表类型", "default": "bar"},
                    "title": {"type": "string", "description": "图表标题"},
                    "description": {"type": "string", "description": "图表描述说明"},
                },
                "required": ["data", "chart_type", "title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "knowledge_search",
            "description": "搜索知识库中的税务法规、会计准则和对账指南。用于获取专业知识辅助分析。",
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

# 工具函数映射
TOOL_FUNCTIONS = {
    "sql_executor": sql_executor,
    "metadata_query": metadata_query,
    "chart_generator": chart_generator,
    "knowledge_search": knowledge_search,
}


def _serialize(val):
    """序列化数据库值为JSON兼容格式"""
    if val is None:
        return None
    from decimal import Decimal
    from datetime import date, datetime
    if isinstance(val, Decimal):
        return float(val)
    if isinstance(val, (date, datetime)):
        return str(val)
    return val
