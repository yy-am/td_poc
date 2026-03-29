"""Runtime data-asset context used to ground planning and execution."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import inspect, select

from app.database import AsyncSessionLocal
from app.models.enterprise import EnterpriseInfo
from app.models.semantic import SysSemanticModel

ANALYSIS_KEYWORDS = (
    "差异",
    "对比",
    "对账",
    "分析",
    "原因",
    "风险",
    "趋势",
    "波动",
    "异常",
)

METADATA_KEYWORDS = (
    "多少张表",
    "哪些表",
    "表结构",
    "字段",
    "字段名",
    "列名",
    "schema",
    "metadata",
    "元数据",
)

FACT_KEYWORDS = (
    "收入",
    "利润",
    "税额",
    "税负",
    "金额",
    "明细",
    "排行",
    "最高",
    "最低",
    "多少",
    "哪些企业",
    "哪家企业",
)

DOMAIN_KEYWORDS = tuple(
    dict.fromkeys(
        ANALYSIS_KEYWORDS
        + METADATA_KEYWORDS
        + FACT_KEYWORDS
        + (
            "增值税",
            "所得税",
            "会计",
            "账面",
            "利润表",
            "发票",
            "申报",
            "核验",
            "交叉",
            "调整",
            "折旧",
            "企业",
            "公司",
            "税务",
        )
    )
)

COMMON_PREFIX_WORDS = (
    "请",
    "帮我",
    "帮忙",
    "分析",
    "查看",
    "查询",
    "对比",
    "比较",
    "统计",
    "请问",
    "我想知道",
    "想看",
    "给我",
)

GENERIC_ENTITY_WORDS = {
    "增值税",
    "所得税",
    "会计账面",
    "账面",
    "税账",
    "差异",
    "风险",
    "趋势",
    "公司",
    "企业",
}

QUARTER_TO_MONTHS = {
    1: ("01", "02", "03"),
    2: ("04", "05", "06"),
    3: ("07", "08", "09"),
    4: ("10", "11", "12"),
}


def classify_query_mode(user_query: str) -> dict[str, Any]:
    text = (user_query or "").strip()
    matched_analysis = [kw for kw in ANALYSIS_KEYWORDS if kw in text]
    matched_metadata = [kw for kw in METADATA_KEYWORDS if kw in text]
    matched_facts = [kw for kw in FACT_KEYWORDS if kw in text]

    non_generic_analysis = [kw for kw in matched_analysis if kw != "分析"]

    if matched_metadata and not non_generic_analysis and not ("申报" in text and "账面" in text):
        return {
            "query_mode": "metadata",
            "confidence": "high",
            "matched_keywords": matched_metadata,
        }

    if non_generic_analysis or ("申报" in text and "账面" in text):
        return {
            "query_mode": "analysis",
            "confidence": "high" if len(non_generic_analysis) >= 2 or ("申报" in text and "账面" in text) else "medium",
            "matched_keywords": non_generic_analysis or ["申报", "账面"],
        }
    return {
        "query_mode": "fact_query",
        "confidence": "medium" if matched_facts else "low",
        "matched_keywords": matched_facts or [],
    }


def extract_period_hints(user_query: str) -> dict[str, Any]:
    text = user_query or ""
    hints: dict[str, Any] = {"year": None, "quarter": None, "periods": []}

    year_match = re.search(r"(20\d{2})", text)
    if year_match:
        hints["year"] = int(year_match.group(1))

    quarter_match = re.search(r"Q\s*([1-4])", text, flags=re.IGNORECASE)
    if quarter_match:
        hints["quarter"] = int(quarter_match.group(1))
    else:
        cn_quarter_match = re.search(r"([一二三四1234])季度", text)
        if cn_quarter_match:
            token = cn_quarter_match.group(1)
            hints["quarter"] = {"一": 1, "二": 2, "三": 3, "四": 4}.get(token, int(token))

    if hints["year"] and hints["quarter"]:
        year = hints["year"]
        quarter = hints["quarter"]
        hints["periods"] = [f"{year}-{month}" for month in QUARTER_TO_MONTHS[quarter]]
        return hints

    month_matches = re.findall(r"(20\d{2})[-/年](0?[1-9]|1[0-2])", text)
    if month_matches:
        hints["periods"] = [f"{year}-{int(month):02d}" for year, month in month_matches]
    return hints


def _compact_columns(raw_columns: list[dict[str, Any]]) -> list[dict[str, str]]:
    columns: list[dict[str, str]] = []
    for column in raw_columns[:20]:
        columns.append(
            {
                "name": str(column.get("name") or ""),
                "type": str(column.get("type") or ""),
            }
        )
    return columns


async def _load_table_schema_map(conn: Any, table_names: list[str]) -> list[dict[str, Any]]:
    if not table_names:
        return []

    schema_items: list[dict[str, Any]] = []
    for table_name in table_names:
        def read_columns(sync_conn):
            return inspect(sync_conn).get_columns(table_name)

        try:
            raw_columns = await conn.run_sync(read_columns)
        except Exception:
            raw_columns = []

        column_names = [str(column.get("name") or "") for column in raw_columns]
        schema_items.append(
            {
                "table_name": table_name,
                "columns": _compact_columns(raw_columns),
                "has_taxpayer_id": "taxpayer_id" in column_names,
                "has_enterprise_name": "enterprise_name" in column_names,
                "has_period": "period" in column_names or "tax_period" in column_names,
            }
        )
    return schema_items


def extract_company_fragments(user_query: str) -> list[str]:
    text = (user_query or "").strip()
    if not text:
        return []

    text = re.sub(r"\s+", "", text)
    for prefix in COMMON_PREFIX_WORDS:
        text = re.sub(rf"^{re.escape(prefix)}", "", text)

    fragments: list[str] = []

    before_time = re.search(r"([\u4e00-\u9fff]{2,16})(?=20\d{2}|Q[1-4]|[一二三四1234]季度)", text, flags=re.IGNORECASE)
    if before_time:
        fragments.append(before_time.group(1))

    named_company = re.findall(r"([\u4e00-\u9fff]{2,20}(?:有限公司|集团|公司))", text)
    fragments.extend(named_company)

    cleaned: list[str] = []
    for fragment in fragments:
        candidate = fragment
        for prefix in COMMON_PREFIX_WORDS:
            candidate = re.sub(rf"^{re.escape(prefix)}", "", candidate)
        candidate = candidate.strip("的与和及、，。！？? ")
        if len(candidate) < 2 or candidate in GENERIC_ENTITY_WORDS:
            continue
        if candidate not in cleaned:
            cleaned.append(candidate)
    return cleaned[:3]


def _collect_query_keywords(user_query: str) -> list[str]:
    text = user_query or ""
    keywords = [kw for kw in DOMAIN_KEYWORDS if kw in text]
    ascii_tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", text)
    for token in ascii_tokens:
        if token not in keywords:
            keywords.append(token)
    return keywords


def _score_asset_text(query_keywords: list[str], asset_text: str, query_mode: str) -> tuple[int, list[str]]:
    score = 0
    matched: list[str] = []
    for keyword in query_keywords:
        if keyword and keyword.lower() in asset_text.lower():
            score += 3 if len(keyword) >= 3 else 1
            matched.append(keyword)

    if query_mode == "analysis":
        if any(word in asset_text for word in ("对比", "分析", "核验", "调整", "差异")):
            score += 3
    elif query_mode == "metadata":
        if any(word in asset_text.lower() for word in ("schema", "metadata")):
            score += 2

    return score, matched


async def build_runtime_context(user_query: str) -> dict[str, Any]:
    mode_info = classify_query_mode(user_query)
    period_hints = extract_period_hints(user_query)
    query_keywords = _collect_query_keywords(user_query)
    company_fragments = extract_company_fragments(user_query)

    async with AsyncSessionLocal() as db:
        model_result = await db.execute(
            select(
                SysSemanticModel.name,
                SysSemanticModel.label,
                SysSemanticModel.description,
                SysSemanticModel.source_table,
                SysSemanticModel.yaml_definition,
                SysSemanticModel.status,
            ).where(SysSemanticModel.status == "active")
        )
        models: list[dict[str, Any]] = []
        for name, label, description, source_table, yaml_definition, status in model_result.all():
            asset_text = " ".join(filter(None, [name, label, description, source_table]))
            score, matched = _score_asset_text(query_keywords, asset_text, mode_info["query_mode"])
            models.append(
                {
                    "name": name,
                    "label": label,
                    "description": description or "",
                    "source_table": source_table,
                    "status": status,
                    "has_yaml_definition": bool((yaml_definition or "").strip()),
                    "recommended_tool": "semantic_query" if (yaml_definition or "").strip() else "sql_executor",
                    "score": score,
                    "matched_keywords": matched,
                }
            )

        conn = await db.connection()
        table_names = await conn.run_sync(lambda sync_conn: sorted(inspect(sync_conn).get_table_names()))

        enterprise_candidates: list[dict[str, str]] = []
        for fragment in company_fragments:
            enterprise_result = await db.execute(
                select(EnterpriseInfo.enterprise_name, EnterpriseInfo.taxpayer_id)
                .where(EnterpriseInfo.enterprise_name.like(f"{fragment}%"))
                .limit(5)
            )
            for enterprise_name, taxpayer_id in enterprise_result.all():
                item = {"enterprise_name": enterprise_name, "taxpayer_id": taxpayer_id}
                if item not in enterprise_candidates:
                    enterprise_candidates.append(item)

    models.sort(key=lambda item: (-item["score"], item["name"]))
    relevant_models = [item for item in models if item["score"] > 0][:5]
    if not relevant_models:
        relevant_models = models[:3]

    relevant_table_names: list[str] = []
    for model in relevant_models:
        table_name = model["source_table"]
        if table_name and table_name not in relevant_table_names:
            relevant_table_names.append(table_name)

    for table_name in table_names:
        score, _ = _score_asset_text(query_keywords, table_name, mode_info["query_mode"])
        if score > 0 and table_name not in relevant_table_names:
            relevant_table_names.append(table_name)

    if enterprise_candidates and "enterprise_info" not in relevant_table_names:
        relevant_table_names.append("enterprise_info")

    relevant_tables = relevant_table_names[:8]
    async with AsyncSessionLocal() as db:
        conn = await db.connection()
        relevant_table_schemas = await _load_table_schema_map(conn, relevant_tables)

    guidance: list[str] = []
    if mode_info["query_mode"] == "analysis":
        guidance.append("这是复杂业务分析问题，优先查询事实数据，不要默认走 metadata_query。")
        guidance.append("如果已有收入对比、差异分析、核验结果等事实资产，优先直接利用。")
    elif mode_info["query_mode"] == "metadata":
        guidance.append("这是元数据问题，可以围绕 metadata_query 规划。")
    else:
        guidance.append("这是事实查询问题，优先获取直接支撑答案的数据。")

    if enterprise_candidates:
        guidance.append("企业名称可能是不完整片段；查询事实表前可先用 enterprise_info 解析 taxpayer_id。")

    if period_hints["periods"]:
        guidance.append("用户提到了季度/期间；如果物理表按月存 period，可将季度展开为对应月份。")

    if any(not model["has_yaml_definition"] for model in relevant_models):
        guidance.append("没有 YAML 定义的语义模型不能走 semantic_query，只能把 source_table 当作 SQL 线索。")

    if enterprise_candidates:
        for table_schema in relevant_table_schemas:
            if table_schema["table_name"] != "enterprise_info" and table_schema.get("has_taxpayer_id") and not table_schema.get("has_enterprise_name"):
                guidance.append(
                    f"{table_schema['table_name']} 没有 enterprise_name 时，应通过 taxpayer_id 与 enterprise_info 关联。"
                )
                break

    return {
        "query_mode": mode_info["query_mode"],
        "classification_confidence": mode_info["confidence"],
        "matched_keywords": mode_info["matched_keywords"],
        "all_query_keywords": query_keywords[:20],
        "period_hints": period_hints,
        "company_fragments": company_fragments,
        "enterprise_candidates": enterprise_candidates[:5],
        "relevant_models": relevant_models,
        "relevant_tables": relevant_tables,
        "relevant_table_schemas": relevant_table_schemas,
        "execution_guidance": guidance,
    }


def validate_plan_graph(plan_graph: dict[str, Any], runtime_context: dict[str, Any]) -> list[str]:
    query_mode = runtime_context.get("query_mode")
    nodes = plan_graph.get("nodes") or []
    if not nodes:
        return ["计划图为空。"]

    issues: list[str] = []
    full_text = " ".join(
        str(part)
        for part in (
            plan_graph.get("title", ""),
            plan_graph.get("summary", ""),
            *[
                " ".join(
                    [
                        str(node.get("title", "")),
                        str(node.get("detail", "")),
                        " ".join(node.get("tool_hints") or []),
                    ]
                )
                for node in nodes
            ],
        )
    )
    business_nodes = [
        node
        for node in nodes
        if node.get("kind") in {"query", "analysis", "knowledge", "visualization"}
    ]
    metadata_only = business_nodes and all(
        set(node.get("tool_hints") or []) <= {"metadata_query"} for node in business_nodes
    )

    if query_mode == "analysis":
        if not business_nodes:
            issues.append("复杂分析问题的计划缺少业务数据查询或分析节点。")
        if metadata_only:
            issues.append("复杂分析问题被规划成了纯 metadata_query 路径。")
        if any(word in full_text for word in ("表结构", "字段", "schema", "metadata")) and not any(
            hint in {"sql_executor", "semantic_query", "knowledge_search", "chart_generator"}
            for node in nodes
            for hint in (node.get("tool_hints") or [])
        ):
            issues.append("复杂分析问题的计划过度聚焦表结构，而没有落到业务事实数据。")

    if query_mode == "metadata":
        if any(node.get("kind") in {"analysis", "visualization"} for node in nodes):
            issues.append("元数据问题被规划成了业务分析路径。")

    return issues


def build_runtime_status_text(runtime_context: dict[str, Any]) -> str:
    mode = runtime_context.get("query_mode", "fact_query")
    mode_label = {
        "analysis": "复杂分析",
        "metadata": "元数据查询",
        "fact_query": "事实查询",
    }.get(mode, mode)

    parts = [f"已识别为{mode_label}问题"]

    enterprises = runtime_context.get("enterprise_candidates") or []
    if enterprises:
        parts.append("企业候选：" + "、".join(item["enterprise_name"] for item in enterprises[:3]))

    periods = (runtime_context.get("period_hints") or {}).get("periods") or []
    if periods:
        parts.append("期间：" + " / ".join(periods[:3]))

    models = [item for item in (runtime_context.get("relevant_models") or []) if item.get("score", 0) > 0]
    if models:
        labels = []
        for item in models[:3]:
            tool = "语义" if item.get("recommended_tool") == "semantic_query" else "SQL"
            labels.append(f"{item['label']}({tool})")
        parts.append("候选资产：" + "、".join(labels))

    return "；".join(parts) + "。"
