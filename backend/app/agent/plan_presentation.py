"""Plan graph normalization and user-facing tool summaries."""

from __future__ import annotations

import re
from typing import Any

PLAN_STATUSES = {"pending", "in_progress", "completed", "skipped", "blocked"}
PLAN_KINDS = {
    "goal",
    "schema",
    "query",
    "analysis",
    "knowledge",
    "visualization",
    "answer",
    "task",
}

TOOL_CATALOG: dict[str, dict[str, str]] = {
    "sql_executor": {
        "label": "查询业务数据",
        "summary": "执行只读 SQL，从税务、账务、对账或指标表中提取事实数据。",
    },
    "semantic_query": {
        "label": "按语义模型取数",
        "summary": "通过语义模型把指标、维度和筛选条件编译成查询，减少手写 SQL。",
    },
    "mql_query": {
        "label": "按 TDA-MQL 取数",
        "summary": "先生成受控的 TDA-MQL，再由语义引擎编译执行，适合指标语义明确的主路径查询。",
    },
    "metadata_query": {
        "label": "查看表结构",
        "summary": "查看当前系统的表清单，或核对某张表的字段结构。",
    },
    "chart_generator": {
        "label": "生成图表",
        "summary": "把结果转换为前端可直接渲染的 ECharts 配置。",
    },
    "knowledge_search": {
        "label": "检索业务规则",
        "summary": "补充税务、会计和对账规则，帮助解释差异原因。",
    },
}

TOOL_HINT_ALIASES = {
    "knowledge_base": "knowledge_search",
    "tax_data_query": "semantic_query",
    "accounting_data_query": "semantic_query",
    "difference_analysis": "sql_executor",
    "risk_assessment": "knowledge_search",
}


def build_fallback_plan_graph(user_query: str) -> dict[str, Any]:
    """Fallback plan used only when model planning fails."""
    focus = infer_semantic_context_from_text(user_query)
    subject = focus["semantic_subject"] or "当前问题"
    return {
        "title": f"{subject}执行计划",
        "summary": "规划调用失败，暂时使用保底路径继续执行。",
        "nodes": [
            {
                "id": "n1",
                "title": f"澄清{subject}目标",
                "detail": "确认问题关注的主体、期间、指标和输出形式。",
                "status": "completed",
                "kind": "goal",
                "depends_on": [],
                "tool_hints": [],
                "done_when": "已明确查询范围和结果口径。",
            },
            {
                "id": "n2",
                "title": f"核对{subject}口径",
                "detail": "如字段或表不明确，先查看结构；否则直接进入取数。",
                "status": "in_progress",
                "kind": "schema",
                "depends_on": ["n1"],
                "tool_hints": ["metadata_query"],
                "done_when": "已确定要访问的表、字段和筛选条件。",
            },
            {
                "id": "n3",
                "title": f"提取{subject}数据",
                "detail": "优先按事实数据验证问题中的关键指标和差异。",
                "status": "pending",
                "kind": "query",
                "depends_on": ["n2"],
                "tool_hints": ["semantic_query", "sql_executor"],
                "done_when": "已获得支持结论的关键数据。",
            },
            {
                "id": "n4",
                "title": f"交付{subject}结论",
                "detail": "整理结论、关键数字、原因与建议，必要时附图表。",
                "status": "pending",
                "kind": "answer",
                "depends_on": ["n3"],
                "tool_hints": ["chart_generator"],
                "done_when": "已形成可直接阅读的最终回答。",
            },
        ],
        "edges": [
            {"source": "n1", "target": "n2"},
            {"source": "n2", "target": "n3"},
            {"source": "n3", "target": "n4"},
        ],
        "active_node_ids": ["n2"],
        "change_reason": "模型计划不可用，使用保底路径继续执行。",
        "source": "fallback",
    }


def normalize_plan_graph(raw_plan: Any, user_query: str) -> dict[str, Any]:
    if not isinstance(raw_plan, dict):
        return build_fallback_plan_graph(user_query)

    raw_nodes = raw_plan.get("nodes")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        return build_fallback_plan_graph(user_query)

    nodes: list[dict[str, Any]] = []
    valid_ids: list[str] = []
    for index, raw_node in enumerate(raw_nodes[:6], start=1):
        if not isinstance(raw_node, dict):
            continue
        node_id = clean_text(str(raw_node.get("id") or f"n{index}"), max_len=24) or f"n{index}"
        if node_id in valid_ids:
            node_id = f"{node_id}_{index}"

        title = clean_text(str(raw_node.get("title") or f"步骤{index}"), max_len=28) or f"步骤{index}"
        detail = clean_text(str(raw_node.get("detail") or raw_node.get("description") or title), max_len=200) or title
        status = str(raw_node.get("status") or "pending").strip().lower()
        kind = str(raw_node.get("kind") or "task").strip().lower()

        nodes.append(
            {
                "id": node_id,
                "title": title,
                "detail": detail,
                "status": status if status in PLAN_STATUSES else "pending",
                "kind": kind if kind in PLAN_KINDS else "task",
                "depends_on": [],
                "tool_hints": normalize_tool_hints(raw_node.get("tool_hints")),
                "done_when": clean_text(str(raw_node.get("done_when") or ""), max_len=120),
                "semantic_binding": normalize_semantic_binding(raw_node.get("semantic_binding")),
            }
        )
        valid_ids.append(node_id)

    if not nodes:
        return build_fallback_plan_graph(user_query)

    for node, raw_node in zip(nodes, raw_nodes[: len(nodes)]):
        raw_deps = raw_node.get("depends_on")
        if isinstance(raw_deps, list):
            deps = [str(dep) for dep in raw_deps if str(dep) in valid_ids and str(dep) != node["id"]]
        else:
            deps = []
        node["depends_on"] = deps

    edges = normalize_plan_edges(raw_plan.get("edges"), nodes)
    if not edges:
        edges = build_edges_from_dependencies(nodes)

    active_node_ids = [
        str(node_id)
        for node_id in raw_plan.get("active_node_ids", [])
        if str(node_id) in valid_ids
    ]
    if not active_node_ids:
        active_node_ids = [node["id"] for node in nodes if node["status"] == "in_progress"][:1]
    if not active_node_ids:
        active_node_ids = [node["id"] for node in nodes if node["status"] == "pending"][:1]
    if not active_node_ids:
        active_node_ids = [nodes[-1]["id"]]

    title = clean_text(str(raw_plan.get("title") or ""), max_len=40)
    if not title:
        focus = infer_semantic_context_from_text(
            " ".join([user_query, *(node["title"] + " " + node["detail"] for node in nodes)])
        )
        title = f"{focus['semantic_subject'] or '当前问题'}执行计划"

    summary = clean_text(str(raw_plan.get("summary") or ""), max_len=200)
    if not summary:
        summary = nodes[0]["detail"]

    change_reason = clean_text(str(raw_plan.get("change_reason") or ""), max_len=200)
    source = str(raw_plan.get("source") or "llm")

    return {
        "title": title,
        "summary": summary,
        "nodes": nodes,
        "edges": edges,
        "active_node_ids": active_node_ids,
        "change_reason": change_reason,
        "source": source,
    }


def build_plan_metadata(
    plan_graph: dict[str, Any],
    title: str | None = None,
    change_reason: str | None = None,
) -> dict[str, Any]:
    semantic_context = extract_plan_context(plan_graph)
    return {
        "plan_title": title or plan_graph.get("title") or "执行计划",
        "plan_items": plan_graph_to_items(plan_graph),
        "plan_graph": plan_graph,
        "change_reason": change_reason or plan_graph.get("change_reason") or "",
        "plan_source": plan_graph.get("source", "llm"),
        "semantic_context": semantic_context,
        "semantic_domain": semantic_context.get("dataset_domain"),
        "semantic_subject": semantic_context.get("semantic_subject"),
        "semantic_mode": semantic_context.get("request_mode"),
    }


def plan_graph_signature(plan_graph: dict[str, Any]) -> tuple[Any, ...]:
    return (
        tuple(
            (
                node.get("id"),
                node.get("title"),
                node.get("status"),
                tuple(node.get("depends_on") or []),
            )
            for node in plan_graph.get("nodes", [])
        ),
        tuple(plan_graph.get("active_node_ids") or []),
    )


def select_plan_node(plan_graph: dict[str, Any], plan_node_id: str | None = None) -> dict[str, Any] | None:
    nodes = plan_graph.get("nodes") or []
    if plan_node_id:
        for node in nodes:
            if node.get("id") == plan_node_id:
                return node

    active_ids = plan_graph.get("active_node_ids") or []
    for node_id in active_ids:
        for node in nodes:
            if node.get("id") == node_id:
                return node

    for node in nodes:
        if node.get("status") == "in_progress":
            return node
    for node in nodes:
        if node.get("status") == "pending":
            return node
    return nodes[0] if nodes else None


def attach_plan_context(
    plan_graph: dict[str, Any] | None,
    plan_node_id: str | None = None,
) -> dict[str, Any]:
    if not plan_graph:
        semantic_context = infer_semantic_context_from_text("")
        return {
            "plan_node_id": plan_node_id,
            "plan_node_title": "",
            "semantic_context": semantic_context,
            "semantic_domain": semantic_context.get("dataset_domain"),
            "semantic_subject": semantic_context.get("semantic_subject"),
            "semantic_mode": semantic_context.get("request_mode"),
            "semantic_binding": {},
        }

    node = select_plan_node(plan_graph, plan_node_id)
    semantic_context = extract_plan_context(plan_graph, node)
    return {
        "plan_node_id": node.get("id") if node else plan_node_id,
        "plan_node_title": node.get("title") if node else "",
        "plan_source": plan_graph.get("source", "llm"),
        "semantic_context": semantic_context,
        "semantic_domain": semantic_context.get("dataset_domain"),
        "semantic_subject": semantic_context.get("semantic_subject"),
        "semantic_mode": semantic_context.get("request_mode"),
        "semantic_binding": normalize_semantic_binding((node or {}).get("semantic_binding")),
    }


def summarize_tool_action(
    tool_name: str,
    tool_args: dict[str, Any],
    plan_graph: dict[str, Any] | None = None,
    plan_node_id: str | None = None,
) -> dict[str, Any]:
    tool_info = TOOL_CATALOG.get(
        tool_name,
        {"label": tool_name, "summary": "执行一个辅助分析动作。"},
    )
    metadata = {
        "tool_name": tool_name,
        "tool_label": tool_info["label"],
        "tool_summary": tool_info["summary"],
        "tool_input": tool_args,
        "tool_input_summary": summarize_tool_input(tool_name, tool_args),
    }
    metadata.update(attach_plan_context(plan_graph, plan_node_id))

    sql_query = tool_args.get("query") if isinstance(tool_args, dict) else None
    if sql_query:
        metadata["sql_preview"] = sql_query
        metadata["sql_summary"] = describe_sql_purpose(sql_query, metadata)

    return metadata


def summarize_observation_metadata(
    tool_name: str,
    result: Any,
    duration_ms: int,
    plan_graph: dict[str, Any] | None = None,
    plan_node_id: str | None = None,
) -> dict[str, Any]:
    metadata = {
        "tool_name": tool_name,
        "tool_label": TOOL_CATALOG.get(tool_name, {}).get("label", tool_name),
        "duration_ms": duration_ms,
        "result_summary": summarize_tool_result(tool_name, result),
    }
    metadata.update(attach_plan_context(plan_graph, plan_node_id))

    if isinstance(result, dict):
        if result.get("sql"):
            metadata["sql"] = result["sql"]
            metadata["sql_summary"] = describe_sql_purpose(result["sql"], metadata)
        if result.get("chart_config"):
            metadata["chart_config"] = result["chart_config"]
        if "columns" in result and "rows" in result:
            metadata["table_data"] = {
                "columns": result["columns"],
                "rows": result["rows"][:20],
            }

    return metadata


def summarize_tool_input(tool_name: str, tool_args: dict[str, Any]) -> str:
    if tool_name == "metadata_query":
        table_name = tool_args.get("table_name")
        return f"准备查看 `{table_name}` 的表结构和字段定义。" if table_name else "准备查看当前系统中的表清单。"

    if tool_name == "sql_executor":
        return describe_sql_purpose(tool_args.get("query", ""))

    if tool_name == "semantic_query":
        model_name = tool_args.get("model_name") or "目标语义模型"
        metrics = ", ".join(tool_args.get("metrics") or []) or "指标"
        entity_filters = tool_args.get("entity_filters") or {}
        resolved_filters = tool_args.get("resolved_filters") or {}
        filter_bits: list[str] = []
        if entity_filters:
            filter_bits.append(f"业务过滤 {entity_filters}")
        if resolved_filters:
            filter_bits.append(f"已解析过滤 {resolved_filters}")
        suffix = f"，{'; '.join(filter_bits)}" if filter_bits else ""
        return f"准备基于 `{model_name}` 提取 {metrics}{suffix}。"

    if tool_name == "mql_query":
        model_name = tool_args.get("model_name") or "目标语义模型"
        metrics = ", ".join(
            str(item.get("metric") or "").strip()
            for item in (tool_args.get("select") or [])
            if isinstance(item, dict) and str(item.get("metric") or "").strip()
        ) or "指标"
        group_by = ", ".join(tool_args.get("group_by") or [])
        entity_filters = tool_args.get("entity_filters") or {}
        time_context = tool_args.get("time_context") or {}
        summary_bits: list[str] = []
        if group_by:
            summary_bits.append(f"按 {group_by}")
        if entity_filters:
            summary_bits.append(f"实体过滤 {entity_filters}")
        if time_context:
            summary_bits.append(f"时间语义 {time_context}")
        suffix = f"，{'；'.join(summary_bits)}" if summary_bits else ""
        return f"准备基于 `{model_name}` 的 TDA-MQL 提取 {metrics}{suffix}。"

    if tool_name == "chart_generator":
        chart_type = tool_args.get("chart_type", "bar")
        title = tool_args.get("title") or "未命名图表"
        return f"准备生成一个 `{chart_type}` 图，标题是“{title}”。"

    if tool_name == "knowledge_search":
        query = tool_args.get("query") or ""
        return f"准备检索与“{query}”相关的业务规则。"

    return "准备执行一个辅助分析动作。"


def summarize_tool_result(tool_name: str, result: Any) -> str:
    if isinstance(result, dict) and result.get("error"):
        return f"工具执行失败：{result['error']}"

    if tool_name == "metadata_query" and isinstance(result, dict):
        if result.get("tables") is not None:
            return f"已获取系统表清单，共 {result.get('count', len(result.get('tables', [])))} 张表。"
        if result.get("columns") is not None:
            return f"已获取 `{result.get('table_name', '目标表')}` 的字段信息，共 {len(result.get('columns', []))} 个字段。"

    if tool_name in {"sql_executor", "semantic_query", "mql_query"} and isinstance(result, dict):
        row_count = result.get("row_count", 0)
        if row_count == 0:
            return "查询已执行，但当前筛选条件下没有返回数据。"
        return f"查询已执行，返回 {row_count} 行结果，可继续分析。"

    if tool_name == "chart_generator" and isinstance(result, dict):
        chart_type = result.get("chart_type", "图表")
        return f"已生成 `{chart_type}` 图配置，前端可直接渲染。"

    if tool_name == "knowledge_search" and isinstance(result, list):
        return f"已检索到 {len(result)} 条业务规则或知识片段。"

    return "步骤已完成，结果已返回。"


def describe_sql_purpose(query: str, context: dict[str, Any] | None = None) -> str:
    if not query:
        return "准备执行 SQL 查询。"

    normalized = re.sub(r"\s+", " ", query.strip())
    upper_query = normalized.upper()
    tables = extract_tables(normalized)
    table_desc = "、".join(f"`{name}`" for name in tables[:3]) if tables else "目标数据表"

    if any(keyword in upper_query for keyword in ("SUM(", "AVG(", "MAX(", "MIN(")):
        action = "汇总关键指标"
    elif "GROUP BY" in upper_query:
        action = "按维度分组分析"
    elif "ORDER BY" in upper_query and "LIMIT" in upper_query:
        action = "做排行或排序分析"
    elif "COUNT(" in upper_query:
        action = "统计记录数量"
    else:
        action = "查看明细结果"

    filters: list[str] = []
    periods = re.findall(r"\b20\d{2}-\d{2}\b", normalized)
    if periods:
        filters.append("期间 " + "、".join(periods[:2]))
    if "TAXPAYER_ID" in upper_query:
        filters.append("企业范围")
    limit_match = re.search(r"\bLIMIT\s+(\d+)", upper_query)
    if limit_match:
        filters.append(f"最多返回 {limit_match.group(1)} 行")

    subject = ""
    if context:
        subject = context.get("plan_node_title") or context.get("semantic_subject") or ""
    prefix = f"围绕“{subject}”" if subject else ""
    suffix = f"，重点关注{'、'.join(filters)}" if filters else ""
    return f"这条 SQL 正在从 {table_desc} 中{prefix}{action}{suffix}。"


def extract_tables(query: str) -> list[str]:
    matches = re.findall(r"\b(?:FROM|JOIN)\s+([A-Za-z_][A-Za-z0-9_]*)", query, flags=re.IGNORECASE)
    tables: list[str] = []
    for name in matches:
        if name not in tables:
            tables.append(name)
    return tables


def plan_graph_to_items(plan_graph: dict[str, Any]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for node in plan_graph.get("nodes", []):
        items.append(
            {
                "key": str(node.get("id")),
                "title": str(node.get("title", "")),
                "detail": str(node.get("detail", "")),
                "status": str(node.get("status", "pending")),
            }
        )
    return items


def extract_plan_context(
    plan_graph: dict[str, Any] | None,
    current_node: dict[str, Any] | None = None,
) -> dict[str, Any]:
    node = current_node or (select_plan_node(plan_graph) if plan_graph else None)
    plan_title = str((plan_graph or {}).get("title") or "")
    node_title = str((node or {}).get("title") or "")
    node_detail = str((node or {}).get("detail") or "")
    focus = infer_semantic_context_from_text(" ".join([plan_title, node_title, node_detail]).strip())

    kind = str((node or {}).get("kind") or "").lower()
    request_mode = focus["request_mode"]
    request_mode_label = focus["request_mode_label"]
    if kind == "schema":
        request_mode = "schema"
        request_mode_label = "查看结构"
    elif kind == "query":
        request_mode = "query"
        request_mode_label = "提取数据"
    elif kind == "analysis":
        request_mode = "analysis"
        request_mode_label = "分析整理"
    elif kind == "knowledge":
        request_mode = "knowledge"
        request_mode_label = "检索规则"
    elif kind == "visualization":
        request_mode = "chart"
        request_mode_label = "生成图表"
    elif kind == "answer":
        request_mode = "answer"
        request_mode_label = "输出结论"

    return {
        "dataset_domain": focus["dataset_domain"],
        "dataset_domain_label": focus["dataset_domain_label"],
        "request_mode": request_mode,
        "request_mode_label": request_mode_label,
        "focus_label": node_title or plan_title or "当前步骤",
        "semantic_subject": node_title or focus["semantic_subject"] or plan_title or "当前问题",
    }


def infer_semantic_context_from_text(text: str) -> dict[str, str]:
    text = text or ""
    lower = text.lower()

    has_tax = bool(re.search(r"tax|vat|invoice|declaration|税|申报|纳税|发票|税负|进项|销项", lower))
    has_accounting = bool(re.search(r"acct|ledger|journal|voucher|balance|income|账|会计|凭证|总账|科目|报表", lower))
    has_recon = bool(re.search(r"recon|difference|compare|diff|对账|差异|比对", lower))
    has_risk = bool(re.search(r"risk|warning|alert|风险|预警", lower))

    if has_recon or (has_tax and has_accounting):
        dataset_domain = "reconciliation"
        dataset_domain_label = "税账对账"
        semantic_subject = "税账差异"
    elif has_tax:
        dataset_domain = "tax"
        dataset_domain_label = "税务数据"
        semantic_subject = "税务数据"
    elif has_accounting:
        dataset_domain = "accounting"
        dataset_domain_label = "账务数据"
        semantic_subject = "账务数据"
    elif has_risk:
        dataset_domain = "risk"
        dataset_domain_label = "风险数据"
        semantic_subject = "风险数据"
    else:
        dataset_domain = "business"
        dataset_domain_label = "业务数据"
        semantic_subject = "业务数据"

    if re.search(r"schema|field|column|表结构|字段|元数据|哪些表|列名", lower):
        request_mode = "schema"
        request_mode_label = "查看结构"
    elif re.search(r"chart|graph|plot|图表|趋势|占比|排行|可视化", lower):
        request_mode = "chart"
        request_mode_label = "图表呈现"
    elif re.search(r"rule|knowledge|policy|规则|口径|依据|知识", lower):
        request_mode = "knowledge"
        request_mode_label = "检索规则"
    elif re.search(r"analysis|reason|compare|difference|anomaly|分析|原因|差异|异常|结论", lower):
        request_mode = "analysis"
        request_mode_label = "分析整理"
    else:
        request_mode = "query"
        request_mode_label = "提取数据"

    return {
        "dataset_domain": dataset_domain,
        "dataset_domain_label": dataset_domain_label,
        "request_mode": request_mode,
        "request_mode_label": request_mode_label,
        "semantic_subject": semantic_subject,
    }


def normalize_plan_edges(raw_edges: Any, nodes: list[dict[str, Any]]) -> list[dict[str, str]]:
    valid_ids = {node["id"] for node in nodes}
    edges: list[dict[str, str]] = []
    if isinstance(raw_edges, list):
        for raw_edge in raw_edges:
            if not isinstance(raw_edge, dict):
                continue
            source = str(raw_edge.get("source") or "")
            target = str(raw_edge.get("target") or "")
            if source in valid_ids and target in valid_ids and source != target:
                edges.append({"source": source, "target": target})
    return dedupe_edges(edges)


def build_edges_from_dependencies(nodes: list[dict[str, Any]]) -> list[dict[str, str]]:
    edges: list[dict[str, str]] = []
    for index, node in enumerate(nodes):
        depends_on = node.get("depends_on") or []
        if depends_on:
            for source in depends_on:
                edges.append({"source": source, "target": node["id"]})
        elif index > 0:
            edges.append({"source": nodes[index - 1]["id"], "target": node["id"]})
    return dedupe_edges(edges)


def dedupe_edges(edges: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    deduped: list[dict[str, str]] = []
    for edge in edges:
        key = (edge["source"], edge["target"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(edge)
    return deduped


def normalize_tool_hints(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    hints: list[str] = []
    for item in value[:3]:
        raw_hint = clean_text(str(item), max_len=32)
        hint = TOOL_HINT_ALIASES.get(raw_hint, raw_hint)
        if hint:
            hints.append(hint)
    return hints


def _normalize_filter_map(value: Any) -> dict[str, list[Any]]:
    if not isinstance(value, dict):
        return {}

    normalized: dict[str, list[Any]] = {}
    for raw_key, raw_value in value.items():
        key = clean_text(str(raw_key or ""), max_len=60)
        if not key:
            continue
        values = raw_value if isinstance(raw_value, list) else [raw_value]
        items: list[Any] = []
        for item in values:
            if item is None or item in items:
                continue
            items.append(item)
        if items:
            normalized[key] = items[:12]
    return normalized


def normalize_semantic_binding(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}

    metrics = [clean_text(str(item), max_len=60) for item in value.get("metrics", []) if str(item or "").strip()]
    dimensions = [clean_text(str(item), max_len=60) for item in value.get("dimensions", []) if str(item or "").strip()]

    filters: list[dict[str, Any]] = []
    for item in value.get("filters", []) or []:
        if not isinstance(item, dict):
            continue
        field = clean_text(str(item.get("field") or ""), max_len=60)
        op = clean_text(str(item.get("op") or ""), max_len=24)
        if not field or not op:
            continue
        filters.append({"field": field, "op": op, "value": item.get("value")})

    legacy_models = [clean_text(str(item), max_len=60) for item in value.get("models", []) if str(item or "").strip()]
    entry_model = clean_text(str(value.get("entry_model") or ""), max_len=60)
    supporting_models = [
        clean_text(str(item), max_len=60)
        for item in value.get("supporting_models", [])
        if str(item or "").strip()
    ]
    if not entry_model and legacy_models:
        entry_model = legacy_models[0]
    if not supporting_models and len(legacy_models) > 1:
        supporting_models = legacy_models[1:]

    entity_filters = _normalize_filter_map(value.get("entity_filters"))
    resolved_filters = _normalize_filter_map(value.get("resolved_filters"))

    if not entity_filters and not resolved_filters:
        for item in filters:
            field = str(item.get("field") or "")
            filter_value = item.get("value")
            values = filter_value if isinstance(filter_value, list) else [filter_value]
            values = [item for item in values if item is not None]
            if not values:
                continue
            if field in {"enterprise_name", "enterprise_names"}:
                entity_filters.setdefault("enterprise_name", [])
                for raw in values:
                    if raw not in entity_filters["enterprise_name"]:
                        entity_filters["enterprise_name"].append(raw)
            else:
                resolved_filters.setdefault(field, [])
                for raw in values:
                    if raw not in resolved_filters[field]:
                        resolved_filters[field].append(raw)

    grain = clean_text(str(value.get("grain") or ""), max_len=24)
    query_language = clean_text(str(value.get("query_language") or ""), max_len=24)
    fallback_policy = clean_text(str(value.get("fallback_policy") or ""), max_len=32)
    if not fallback_policy:
        fallback_policy = "atomic_then_sql" if bool(value.get("fallback_to_sql", True)) else "semantic_only"

    time_context = value.get("time_context") if isinstance(value.get("time_context"), dict) else {}
    analysis_mode = value.get("analysis_mode") if isinstance(value.get("analysis_mode"), dict) else {}
    drilldown = value.get("drilldown") if isinstance(value.get("drilldown"), dict) else {}
    compare: dict[str, Any] = {}
    if time_context.get("compare"):
        compare = {
            "enabled": True,
            "label": clean_text(str(time_context.get("compare") or ""), max_len=40),
            "target": clean_text(str(time_context.get("range") or ""), max_len=40),
            "metrics": metrics[:4],
            "dimensions": dimensions[:4],
        }
    if drilldown.get("enabled"):
        drilldown = {
            "enabled": True,
            "target": clean_text(str(drilldown.get("target") or ""), max_len=60),
            "detail_fields": [
                clean_text(str(item), max_len=60)
                for item in (drilldown.get("detail_fields") or [])[:8]
                if str(item or "").strip()
            ],
            "limit": drilldown.get("limit"),
        }
    analysis_mode_payload: dict[str, Any] = dict(analysis_mode)
    if compare.get("enabled") and drilldown.get("enabled"):
        analysis_mode_payload.setdefault("kind", "hybrid")
        analysis_mode_payload.setdefault("label", "混合分析")
    elif compare.get("enabled"):
        analysis_mode_payload.setdefault("kind", "compare")
        analysis_mode_payload.setdefault("label", "对比分析")
    elif drilldown.get("enabled"):
        analysis_mode_payload.setdefault("kind", "drilldown")
        analysis_mode_payload.setdefault("label", "明细下钻")
    else:
        analysis_mode_payload.setdefault("kind", "analysis")
        analysis_mode_payload.setdefault("label", "常规分析")

    return {
        "entry_model": entry_model,
        "supporting_models": supporting_models[:6],
        "metrics": metrics[:8],
        "dimensions": dimensions[:8],
        "entity_filters": entity_filters,
        "resolved_filters": resolved_filters,
        "grain": grain,
        "query_language": query_language,
        "time_context": time_context,
        "analysis_mode": analysis_mode_payload,
        "compare": compare,
        "drilldown": drilldown,
        "fallback_policy": fallback_policy,
        "filters": filters[:8],
    }


def clean_text(text: str, max_len: int = 120) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text[:max_len]
