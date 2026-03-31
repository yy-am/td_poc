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
            "汇算清缴",
            "汇缴",
            "桥接",
            "应纳税所得额",
            "应补退税额",
            "应纳所得税额",
            "预缴税额",
            "进项",
            "销项",
            "转出",
            "税负",
            "诊断",
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


def _merge_string_lists(primary: list[str], secondary: list[str]) -> list[str]:
    merged: list[str] = []
    for item in primary + secondary:
        text = str(item or "").strip()
        if text and text not in merged:
            merged.append(text)
    return merged


def _merge_period_hints(
    inferred_hints: dict[str, Any],
    understanding_result: dict[str, Any] | None,
) -> dict[str, Any]:
    hints = {
        "year": inferred_hints.get("year"),
        "quarter": inferred_hints.get("quarter"),
        "periods": list(inferred_hints.get("periods") or []),
    }
    understanding_entities = ((understanding_result or {}).get("entities") or {})
    for period in understanding_entities.get("periods", []) or []:
        text = str(period or "").strip()
        if text and text not in hints["periods"]:
            hints["periods"].append(text)
    return hints


async def build_runtime_context(
    user_query: str,
    understanding_result: dict[str, Any] | None = None,
    semantic_grounding: dict[str, Any] | None = None,
) -> dict[str, Any]:
    heuristic_mode = classify_query_mode(user_query)
    mode_info = {
        "query_mode": str((understanding_result or {}).get("query_mode") or heuristic_mode["query_mode"]),
        "confidence": str((understanding_result or {}).get("confidence") or heuristic_mode["confidence"]),
        "matched_keywords": heuristic_mode["matched_keywords"],
    }
    period_hints = _merge_period_hints(extract_period_hints(user_query), understanding_result)
    query_keywords = _collect_query_keywords(user_query)
    if understanding_result:
        query_keywords = _merge_string_lists(
            query_keywords,
            _merge_string_lists(
                understanding_result.get("metrics", []) or [],
                understanding_result.get("dimensions", []) or [],
            ),
        )
    company_fragments = extract_company_fragments(user_query)
    if understanding_result:
        company_fragments = _merge_string_lists(
            company_fragments,
            ((understanding_result.get("entities") or {}).get("enterprise_names") or []),
        )[:5]

    if semantic_grounding is None:
        async with AsyncSessionLocal() as db:
            model_result = await db.execute(
                select(
                    SysSemanticModel.name,
                    SysSemanticModel.label,
                    SysSemanticModel.description,
                    SysSemanticModel.source_table,
                    SysSemanticModel.model_type,
                    SysSemanticModel.yaml_definition,
                    SysSemanticModel.status,
                ).where(SysSemanticModel.status == "active")
            )
            models: list[dict[str, Any]] = []
            for name, label, description, source_table, model_type, yaml_definition, status in model_result.all():
                asset_text = " ".join(filter(None, [name, label, description, source_table]))
                score, matched = _score_asset_text(query_keywords, asset_text, mode_info["query_mode"])
                has_yaml = bool((yaml_definition or "").strip())
                if has_yaml and model_type == "metric":
                    recommended_tool = "mql_query"
                elif has_yaml:
                    recommended_tool = "semantic_query"
                else:
                    recommended_tool = "sql_executor"
                models.append(
                    {
                        "name": name,
                        "label": label,
                        "description": description or "",
                        "source_table": source_table,
                        "status": status,
                        "has_yaml_definition": has_yaml,
                        "recommended_tool": recommended_tool,
                        "score": score,
                        "matched_keywords": matched,
                        "business_terms": [],
                        "dimensions": [],
                        "metrics": [],
                        "analysis_patterns": [],
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
    else:
        relevant_models = list(semantic_grounding.get("candidate_models") or [])[:6]
        relevant_tables = list(semantic_grounding.get("relevant_tables") or [])[:8]
        relevant_table_schemas = list(semantic_grounding.get("relevant_table_schemas") or [])
        enterprise_candidates = list(semantic_grounding.get("enterprise_candidates") or [])[:5]
        query_keywords = _merge_string_lists(query_keywords, semantic_grounding.get("query_keywords") or [])
        company_fragments = _merge_string_lists(company_fragments, semantic_grounding.get("company_fragments") or [])[:5]

    guidance: list[str] = []
    if understanding_result:
        intent_summary = str(understanding_result.get("intent_summary") or "").strip()
        if intent_summary:
            guidance.append(f"LLM 理解层已识别本次业务目标：{intent_summary}")
        semantic_scope = understanding_result.get("semantic_scope") or {}
        preferred_models = []
        for key in ("composite_models", "atomic_models", "entity_models"):
            for name in semantic_scope.get(key, []) or []:
                text = str(name or "").strip()
                if text and text not in preferred_models:
                    preferred_models.append(text)
        if understanding_result.get("candidate_models"):
            guidance.append(
                "优先围绕理解层选择的语义模型规划和执行："
                + "、".join(str(name) for name in understanding_result.get("candidate_models", [])[:3])
            )
        elif preferred_models:
            guidance.append("优先围绕分层语义范围规划和执行：" + "、".join(preferred_models[:3]))
        resolution_requirements = understanding_result.get("resolution_requirements") or []
        if resolution_requirements:
            guidance.append("执行前需满足的解析要求：" + "；".join(str(item) for item in resolution_requirements[:3]))
    if mode_info["query_mode"] == "analysis":
        guidance.append("这是复杂业务分析问题，优先查询事实数据，不要默认走 metadata_query。")
        guidance.append("如果已有收入对比、差异分析、核验结果等事实资产，优先直接利用。")
        if any(item.get("recommended_tool") == "mql_query" for item in relevant_models):
            guidance.append("若命中指标语义强的复合分析模型，优先显式走 mql_query 主路径。")
    elif mode_info["query_mode"] == "reconciliation":
        guidance.append("这是对账问题，必须同时覆盖至少两个业务口径或两个对比对象，不能只拿单边数据。")
    elif mode_info["query_mode"] == "diagnosis":
        guidance.append("这是诊断/归因问题，不能只停留在差异现象，需补充原因证据或桥接项。")
    elif mode_info["query_mode"] == "metadata":
        guidance.append("这是元数据问题，可以围绕 metadata_query 规划。")
    else:
        guidance.append("这是事实查询问题，优先获取直接支撑答案的数据。")

    if enterprise_candidates:
        guidance.append("企业名称可能是不完整片段；查询事实表前可先用 enterprise_info 解析 taxpayer_id。")

    if period_hints["periods"]:
        guidance.append("用户提到了季度/期间；如果物理表按月存 period，可将季度展开为对应月份。")

    if any(not model["has_yaml_definition"] for model in relevant_models):
        guidance.append("没有 YAML 定义的语义模型不能走 semantic_query 或 mql_query，只能把 source_table 当作 SQL 线索。")

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
        "semantic_catalog_by_kind": (semantic_grounding or {}).get("catalog_by_kind") or {},
        "relevant_tables": relevant_tables,
        "relevant_table_schemas": relevant_table_schemas,
        "execution_guidance": guidance,
        "understanding_result": understanding_result or {},
        "semantic_grounding": semantic_grounding or {},
    }


def _binding_model_names(node: dict[str, Any]) -> set[str]:
    binding = node.get("semantic_binding")
    if not isinstance(binding, dict):
        return set()

    names: set[str] = set()
    for key in ("entry_model",):
        value = str(binding.get(key) or "").strip()
        if value:
            names.add(value)
    for key in ("supporting_models", "models"):
        for item in binding.get(key, []) or []:
            value = str(item or "").strip()
            if value:
                names.add(value)
    return names


def _has_semantic_binding(node: dict[str, Any]) -> bool:
    binding = node.get("semantic_binding")
    if not isinstance(binding, dict):
        return False
    return bool(str(binding.get("entry_model") or "").strip() or (binding.get("models") or []))


def _binding_has_enterprise_filter(node: dict[str, Any]) -> bool:
    binding = node.get("semantic_binding")
    if not isinstance(binding, dict):
        return False

    entity_filters = binding.get("entity_filters") or {}
    resolved_filters = binding.get("resolved_filters") or {}
    if (entity_filters.get("enterprise_name") or entity_filters.get("enterprise_names")):
        return True
    if resolved_filters.get("taxpayer_id"):
        return True

    for item in binding.get("filters", []) or []:
        if not isinstance(item, dict):
            continue
        field = str(item.get("field") or "").strip()
        if field in {"enterprise_name", "enterprise_names", "taxpayer_id"}:
            return True
    return False


def validate_plan_graph(plan_graph: dict[str, Any], runtime_context: dict[str, Any]) -> list[str]:
    query_mode = runtime_context.get("query_mode")
    understanding_result = runtime_context.get("understanding_result") or {}
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
    semantic_ready_models = [
        item["name"]
        for item in (runtime_context.get("relevant_models") or [])
        if item.get("has_yaml_definition") and item.get("name")
    ]
    semantic_bound = any(_has_semantic_binding(node) for node in business_nodes)

    if query_mode == "analysis":
        if not business_nodes:
            issues.append("复杂分析问题的计划缺少业务数据查询或分析节点。")
        if metadata_only:
            issues.append("复杂分析问题被规划成了纯 metadata_query 路径。")
        if any(word in full_text for word in ("表结构", "字段", "schema", "metadata")) and not any(
            hint in {"sql_executor", "semantic_query", "mql_query", "knowledge_search", "chart_generator"}
            for node in nodes
            for hint in (node.get("tool_hints") or [])
        ):
            issues.append("复杂分析问题的计划过度聚焦表结构，而没有落到业务事实数据。")
        if semantic_ready_models and not semantic_bound:
            issues.append("复杂分析问题的计划缺少 semantic_binding，未显式绑定可用语义模型。")

    if query_mode in {"fact_query", "reconciliation", "diagnosis"} and semantic_ready_models and not metadata_only:
        if not semantic_bound:
            issues.append("当前问题已有可用语义模型，但计划未显式绑定 semantic_binding。")

    if query_mode in {"fact_query", "analysis", "reconciliation", "diagnosis"}:
        for node in business_nodes:
            if node.get("kind") not in {"query", "analysis"}:
                continue
            binding = node.get("semantic_binding") if isinstance(node.get("semantic_binding"), dict) else {}
            if binding and not str(binding.get("entry_model") or "").strip() and not (binding.get("models") or []):
                issues.append("业务查询节点存在不完整 semantic_binding：缺少 entry_model。")
                break

    enterprise_names = set(str(name) for name in ((understanding_result.get("entities") or {}).get("enterprise_names") or []) if name)
    for item in runtime_context.get("enterprise_candidates") or []:
        value = str(item.get("enterprise_name") or "").strip()
        if value:
            enterprise_names.add(value)
    if enterprise_names and query_mode in {"fact_query", "analysis", "reconciliation", "diagnosis"}:
        for node in business_nodes:
            if node.get("kind") not in {"query", "analysis"}:
                continue
            if _has_semantic_binding(node) and not _binding_has_enterprise_filter(node):
                issues.append("用户已指定企业，但业务查询节点的 semantic_binding 缺少 enterprise_name/taxpayer_id 过滤。")
                break

    if query_mode == "metadata":
        if any(node.get("kind") in {"analysis", "visualization"} for node in nodes):
            issues.append("元数据问题被规划成了业务分析路径。")

    candidate_models = set(str(name) for name in understanding_result.get("candidate_models", []) if name)
    semantic_scope = understanding_result.get("semantic_scope") or {}
    for key in ("entity_models", "atomic_models", "composite_models"):
        for name in semantic_scope.get(key, []) or []:
            value = str(name or "").strip()
            if value:
                candidate_models.add(value)
    if candidate_models and semantic_bound:
        bound_models = set()
        for node in business_nodes:
            bound_models.update(_binding_model_names(node))
        if bound_models and bound_models.isdisjoint(candidate_models):
            issues.append("计划绑定的语义模型与理解层推荐模型不一致。")

    return issues


def build_runtime_status_text(runtime_context: dict[str, Any]) -> str:
    mode = runtime_context.get("query_mode", "fact_query")
    mode_label = {
        "analysis": "复杂分析",
        "metadata": "元数据查询",
        "fact_query": "事实查询",
        "reconciliation": "对账分析",
        "diagnosis": "诊断归因",
    }.get(mode, mode)

    parts = [f"已识别为{mode_label}问题"]
    understanding_result = runtime_context.get("understanding_result") or {}
    intent_summary = str(understanding_result.get("intent_summary") or "").strip()
    if intent_summary:
        parts.append("理解目标：" + intent_summary)

    enterprises = runtime_context.get("enterprise_candidates") or []
    if enterprises:
        parts.append("企业候选：" + "、".join(item["enterprise_name"] for item in enterprises[:3]))

    periods = (runtime_context.get("period_hints") or {}).get("periods") or []
    if periods:
        parts.append("期间：" + " / ".join(periods[:3]))

    semantic_scope = understanding_result.get("semantic_scope") or {}
    preferred_entry = ""
    for key in ("composite_models", "atomic_models", "entity_models"):
        models = semantic_scope.get(key) or []
        if models:
            preferred_entry = str(models[0])
            break
    if preferred_entry:
        parts.append("优先入口模型：" + preferred_entry)

    models = [item for item in (runtime_context.get("relevant_models") or []) if item.get("score", 0) > 0]
    if models:
        labels = []
        for item in models[:3]:
            tool = {
                "semantic_query": "语义",
                "mql_query": "MQL",
            }.get(item.get("recommended_tool"), "SQL")
            labels.append(f"{item['label']}({tool})")
        parts.append("候选资产：" + "、".join(labels))

    ambiguities = understanding_result.get("ambiguities") or []
    if ambiguities:
        parts.append("待确认：" + "；".join(str(item) for item in ambiguities[:2]))

    return "；".join(parts) + "。"
