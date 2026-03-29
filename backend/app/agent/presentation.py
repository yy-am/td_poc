"""Helpers for user-friendly agent plans and tool explanations."""

from __future__ import annotations

import re
from typing import Any


TOOL_CATALOG: dict[str, dict[str, str]] = {
    "sql_executor": {
        "label": "查询业务数据",
        "summary": "执行只读 SQL，从税务、财务或对账表中提取分析所需的数据。",
    },
    "metadata_query": {
        "label": "查看数据表结构",
        "summary": "查看当前系统有哪些表，或确认某张表有哪些字段。",
    },
    "chart_generator": {
        "label": "生成图表",
        "summary": "把查询结果整理成前端可直接渲染的图表配置。",
    },
    "knowledge_search": {
        "label": "检索业务知识",
        "summary": "补充税务、会计和对账规则，帮助解释差异原因。",
    },
}


def build_initial_plan(user_query: str) -> list[dict[str, str]]:
    wants_chart = any(
        keyword in user_query
        for keyword in ("图", "图表", "可视化", "趋势", "占比", "排行", "柱状", "折线", "饼图")
    )
    wants_metadata = any(
        keyword in user_query
        for keyword in ("表", "字段", "schema", "结构", "元数据", "多少张表", "有哪些表")
    )

    inspect_detail = (
        "先确认涉及哪些表和字段，避免直接查询错表。"
        if wants_metadata
        else "如字段范围不明确，再补查表结构。"
    )
    chart_detail = (
        "如果结果适合可视化，会补一个图表帮助用户更快看懂。"
        if wants_chart
        else "如果结果天然适合图表，会再补一层可视化说明。"
    )

    return [
        _plan_item("understand", "理解问题与确认口径", "识别企业、期间、指标和输出形式。", "in_progress"),
        _plan_item("inspect", "必要时核对表结构", inspect_detail, "pending"),
        _plan_item("query", "提取关键数据", "查询事实数据、汇总结果或明细记录。", "pending"),
        _plan_item("analyze", "分析并整理结论", "对结果做对比、归纳、异常识别和解释。", "pending"),
        _plan_item("chart", "补充图表说明", chart_detail, "pending"),
        _plan_item("answer", "形成最终回答", "先给结论，再给依据、影响和建议。", "pending"),
    ]


def mark_plan_for_tool_start(
    plan_items: list[dict[str, str]], tool_name: str, tool_args: dict[str, Any]
) -> tuple[list[dict[str, str]], str]:
    _mark_status(plan_items, "understand", "completed")

    if tool_name == "metadata_query":
        table_name = tool_args.get("table_name")
        detail = f"正在核对 `{table_name}` 的字段结构。" if table_name else "正在查看当前系统包含哪些表。"
        _mark_status(plan_items, "inspect", "in_progress", detail)
        _mark_status(plan_items, "query", "pending")
        return plan_items, "先确认表结构或表清单，再决定后续查询路径。"

    if tool_name == "sql_executor":
        if _get_item(plan_items, "inspect")["status"] == "pending":
            _mark_status(plan_items, "inspect", "skipped", "字段范围已经足够明确，直接取数更高效。")
        _mark_status(plan_items, "query", "in_progress", describe_sql_purpose(tool_args.get("query", "")))
        return plan_items, "开始提取业务数据，验证问题中的关键事实和指标。"

    if tool_name == "chart_generator":
        _mark_status(plan_items, "query", "completed")
        _mark_status(plan_items, "analyze", "completed")
        _mark_status(plan_items, "chart", "in_progress", "正在把结果转换成图表配置，帮助更直观地展示结论。")
        return plan_items, "数据已经足够，补一个图表让结论更直观。"

    if tool_name == "knowledge_search":
        if _get_item(plan_items, "query")["status"] == "pending":
            _mark_status(plan_items, "query", "skipped", "这一步先补规则背景，不直接查事实数据。")
        _mark_status(plan_items, "analyze", "in_progress", "正在补充税务或会计规则依据。")
        return plan_items, "先补规则依据，再把业务现象解释清楚。"

    return plan_items, "执行新的工具步骤以补足分析证据。"


def mark_plan_for_tool_result(
    plan_items: list[dict[str, str]], tool_name: str, result: Any
) -> tuple[list[dict[str, str]], str]:
    if tool_name == "metadata_query":
        _mark_status(plan_items, "inspect", "completed", summarize_tool_result(tool_name, result))
        _mark_status(plan_items, "query", "pending", "表结构已确认，如需事实数据再进入取数阶段。")
        return plan_items, "元数据已确认，接下来根据需要决定是否取数。"

    if tool_name == "sql_executor":
        _mark_status(plan_items, "query", "completed", summarize_tool_result(tool_name, result))
        _mark_status(plan_items, "analyze", "in_progress", "已拿到关键数据，正在归纳差异、异常或结论。")
        return plan_items, "关键数据已返回，开始整理结论。"

    if tool_name == "chart_generator":
        _mark_status(plan_items, "chart", "completed", summarize_tool_result(tool_name, result))
        _mark_status(plan_items, "answer", "in_progress", "图表已准备好，正在组织最终表达。")
        return plan_items, "图表已生成，接下来整合文字结论。"

    if tool_name == "knowledge_search":
        _mark_status(plan_items, "analyze", "in_progress", summarize_tool_result(tool_name, result))
        return plan_items, "规则依据已补充，继续整理解释和结论。"

    return plan_items, "分析计划已根据最新结果更新。"


def mark_plan_for_final_answer(plan_items: list[dict[str, str]]) -> tuple[list[dict[str, str]], str]:
    _mark_status(plan_items, "understand", "completed")

    for key in ("inspect", "query", "chart"):
        item = _get_item(plan_items, key)
        if item["status"] == "pending":
            _mark_status(plan_items, key, "skipped", "本轮问题不需要这一步，也能给出可靠结论。")
        elif item["status"] == "in_progress":
            _mark_status(plan_items, key, "completed")

    analyze_item = _get_item(plan_items, "analyze")
    if analyze_item["status"] in {"pending", "in_progress"}:
        _mark_status(plan_items, "analyze", "completed", "分析已完成，准备向用户交付结果。")

    _mark_status(plan_items, "answer", "completed", "最终回答已生成。")
    return plan_items, "计划执行完成，下面给出最终结论。"


def build_plan_metadata(
    plan_items: list[dict[str, str]], title: str, change_reason: str | None = None
) -> dict[str, Any]:
    return {
        "plan_title": title,
        "plan_items": [dict(item) for item in plan_items],
        "change_reason": change_reason or "",
    }


def summarize_tool_action(tool_name: str, tool_args: dict[str, Any]) -> dict[str, Any]:
    tool_info = TOOL_CATALOG.get(
        tool_name,
        {"label": tool_name, "summary": "执行一个辅助分析动作。"},
    )

    sql_query = tool_args.get("query") if isinstance(tool_args, dict) else None
    metadata: dict[str, Any] = {
        "tool_name": tool_name,
        "tool_label": tool_info["label"],
        "tool_summary": tool_info["summary"],
        "tool_input": tool_args,
        "tool_input_summary": summarize_tool_input(tool_name, tool_args),
    }

    if sql_query:
        metadata["sql_preview"] = sql_query
        metadata["sql_summary"] = describe_sql_purpose(sql_query)

    return metadata


def summarize_observation_metadata(tool_name: str, result: Any, duration_ms: int) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "tool_name": tool_name,
        "tool_label": TOOL_CATALOG.get(tool_name, {}).get("label", tool_name),
        "duration_ms": duration_ms,
        "result_summary": summarize_tool_result(tool_name, result),
    }

    if isinstance(result, dict):
        if tool_name == "sql_executor" and result.get("sql"):
            metadata["sql"] = result["sql"]
            metadata["sql_summary"] = describe_sql_purpose(result["sql"])
        if tool_name == "chart_generator" and result.get("chart_config"):
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
    if tool_name == "chart_generator":
        chart_type = tool_args.get("chart_type", "bar")
        title = tool_args.get("title") or "未命名图表"
        return f"准备生成一个 `{chart_type}` 图，标题是“{title}”。"
    if tool_name == "knowledge_search":
        query = tool_args.get("query") or ""
        return f"准备检索与“{query}”相关的税务或会计规则。"
    return "准备执行一个辅助分析动作。"


def summarize_tool_result(tool_name: str, result: Any) -> str:
    if isinstance(result, dict) and result.get("error"):
        return f"工具执行失败：{result['error']}"

    if tool_name == "metadata_query" and isinstance(result, dict):
        if result.get("tables") is not None:
            return f"已获取系统表清单，共 {result.get('count', len(result.get('tables', [])))} 张表。"
        if result.get("columns") is not None:
            return f"已获取 `{result.get('table_name', '目标表')}` 的字段信息，共 {len(result.get('columns', []))} 个字段。"

    if tool_name == "sql_executor" and isinstance(result, dict):
        row_count = result.get("row_count", 0)
        if row_count == 0:
            return "SQL 已执行，但当前筛选条件下没有返回数据。"
        return f"SQL 已执行，返回 {row_count} 行结果，可用于继续分析。"

    if tool_name == "chart_generator" and isinstance(result, dict):
        chart_type = result.get("chart_type", "图表")
        return f"已生成 `{chart_type}` 图的配置，前端可以直接渲染。"

    if tool_name == "knowledge_search" and isinstance(result, list):
        return f"已检索到 {len(result)} 条知识片段，可用于补充规则解释。"

    return "步骤已完成，结果已返回。"


def describe_sql_purpose(query: str) -> str:
    if not query:
        return "准备执行 SQL 查询。"

    normalized = re.sub(r"\s+", " ", query.strip())
    upper_query = normalized.upper()
    tables = _extract_tables(normalized)
    table_desc = "、".join(f"`{name}`" for name in tables[:3]) if tables else "目标数据表"

    if "COUNT(" in upper_query and "GROUP BY" not in upper_query:
        action = "统计记录数量"
    elif any(keyword in upper_query for keyword in ("SUM(", "AVG(", "MAX(", "MIN(")):
        action = "汇总关键指标"
    elif "GROUP BY" in upper_query:
        action = "按维度分组汇总"
    elif "ORDER BY" in upper_query and "LIMIT" in upper_query:
        action = "做排序或排行分析"
    else:
        action = "查看明细或中间结果"

    filters: list[str] = []
    periods = re.findall(r"\b20\d{2}-\d{2}\b", normalized)
    if periods:
        filters.append("期间 " + "、".join(periods[:2]))
    if "TAXPAYER_ID" in upper_query:
        filters.append("企业范围")
    if "LIMIT" in upper_query:
        limit_match = re.search(r"\bLIMIT\s+(\d+)", upper_query)
        if limit_match:
            filters.append(f"最多返回 {limit_match.group(1)} 行")

    filter_desc = f"，关注 {', '.join(filters)}" if filters else ""
    return f"这条 SQL 正在从 {table_desc} 中{action}{filter_desc}。"


def _extract_tables(query: str) -> list[str]:
    matches = re.findall(r"\b(?:FROM|JOIN)\s+([A-Za-z_][A-Za-z0-9_]*)", query, flags=re.IGNORECASE)
    tables: list[str] = []
    for name in matches:
        if name not in tables:
            tables.append(name)
    return tables


def _plan_item(key: str, title: str, detail: str, status: str) -> dict[str, str]:
    return {
        "key": key,
        "title": title,
        "detail": detail,
        "status": status,
    }


def _get_item(plan_items: list[dict[str, str]], key: str) -> dict[str, str]:
    for item in plan_items:
        if item["key"] == key:
            return item
    raise KeyError(f"unknown plan key: {key}")


def _mark_status(
    plan_items: list[dict[str, str]], key: str, status: str, detail: str | None = None
) -> None:
    item = _get_item(plan_items, key)
    item["status"] = status
    if detail:
        item["detail"] = detail


# --- Semantic naming overrides -------------------------------------------------

_TAX_KEYWORDS = (
    "税",
    "税务",
    "纳税",
    "发票",
    "申报",
    "税率",
    "税额",
    "税负",
    "增值税",
    "企业所得税",
    "个税",
    "销项",
    "进项",
    "税局",
)

_ACCOUNTING_KEYWORDS = (
    "账",
    "账务",
    "会计",
    "凭证",
    "科目",
    "总账",
    "明细账",
    "日记账",
    "余额",
    "损益",
    "资产负债",
    "应收",
    "应付",
    "财务",
    "对账",
    "报表",
)

_SCHEMA_KEYWORDS = (
    "表结构",
    "字段",
    "列名",
    "schema",
    "结构",
    "元数据",
    "有哪些表",
    "有哪些字段",
    "查看表",
)

_CHART_KEYWORDS = (
    "图",
    "图表",
    "可视化",
    "趋势",
    "占比",
    "排行",
    "排名",
    "分布",
    "柱状",
    "折线",
    "饼图",
    "散点",
)


def build_request_context(
    user_query: str,
    tool_name: str | None = None,
    tool_args: dict[str, Any] | None = None,
    plan_items: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    text_parts = [user_query or ""]
    if tool_args:
        text_parts.extend(str(value) for value in tool_args.values() if value is not None)
    if plan_items:
        text_parts.extend(
            str(item.get("title", "")) + " " + str(item.get("detail", "")) for item in plan_items
        )

    combined = _normalize_semantic_text(" ".join(text_parts))
    table_names = _collect_table_names(tool_args)
    domain = _detect_domain(combined, table_names)
    mode = _detect_request_mode(combined, tool_name)
    subject = _domain_subject(domain)
    focus = _build_focus_label(domain, mode)

    return {
        "query": user_query or "",
        "combined_text": combined,
        "dataset_domain": domain,
        "dataset_domain_label": subject,
        "request_mode": mode,
        "request_mode_label": _mode_label(mode),
        "focus_label": focus,
        "table_names": table_names,
        "semantic_subject": subject,
    }


def extract_plan_context(plan_items: list[dict[str, str]] | None) -> dict[str, Any]:
    if not plan_items:
        return {}

    for item in plan_items:
        context = {
            "dataset_domain": item.get("semantic_domain", ""),
            "dataset_domain_label": item.get("semantic_domain_label", ""),
            "request_mode": item.get("semantic_mode", ""),
            "request_mode_label": item.get("semantic_mode_label", ""),
            "focus_label": item.get("semantic_focus", ""),
            "semantic_subject": item.get("semantic_subject", ""),
        }
        if any(context.values()):
            if not context["dataset_domain_label"]:
                context["dataset_domain_label"] = _domain_subject(context["dataset_domain"])
            if not context["request_mode_label"]:
                context["request_mode_label"] = _mode_label(context["request_mode"])
            if not context["focus_label"]:
                context["focus_label"] = _build_focus_label(
                    context["dataset_domain"], context["request_mode"]
                )
            if not context["semantic_subject"]:
                context["semantic_subject"] = context["dataset_domain_label"] or "业务"
            return context

    first = plan_items[0]
    return {
        "dataset_domain": first.get("semantic_domain", ""),
        "dataset_domain_label": first.get("semantic_domain_label", ""),
        "request_mode": first.get("semantic_mode", ""),
        "request_mode_label": first.get("semantic_mode_label", ""),
        "focus_label": first.get("semantic_focus", ""),
        "semantic_subject": first.get("semantic_subject", ""),
    }


def build_initial_plan(user_query: str) -> list[dict[str, str]]:
    context = build_request_context(user_query)
    domain_label = context["dataset_domain_label"]
    mode = context["request_mode"]
    subject = context["semantic_subject"]
    focus = context["focus_label"]

    wants_schema = mode == "schema"
    wants_chart = mode == "chart"

    inspect_title = f"确认{subject}表结构" if wants_schema else f"核对{subject}字段范围"
    query_title = (
        f"提取{subject}数据"
        if mode != "chart"
        else f"整理{subject}数据"
    )
    chart_title = f"生成{subject}图表" if wants_chart else "补充图表说明"

    inspect_detail = (
        f"先确认{subject}相关表的字段、类型和口径，避免直接查错列。"
        if wants_schema
        else f"核对{subject}相关字段范围，确认后再下发查询。"
    )
    chart_detail = (
        f"如果结果适合可视化，就把{subject}数据整理成图表。"
        if wants_chart
        else "如果结果适合可视化，再补一层图表说明。"
    )

    plan_items = [
        _plan_item(
            "understand",
            "识别问题目标",
            f"判断当前请求是在查看{domain_label or '业务'}数据、表结构还是图表。",
            "in_progress",
        ),
        _plan_item("inspect", inspect_title, inspect_detail, "pending"),
        _plan_item(
            "query",
            query_title,
            f"提取{subject}相关的关键数据、明细或汇总结果。",
            "pending",
        ),
        _plan_item(
            "analyze",
            f"分析{subject}结果",
            f"对{subject}数据做趋势、差异、异常和口径解释。",
            "pending",
        ),
        _plan_item("chart", chart_title, chart_detail, "pending"),
        _plan_item(
            "answer",
            "形成结论",
            "用可读的中文段落给出结论、依据和下一步建议。",
            "pending",
        ),
    ]

    for item in plan_items:
        item["semantic_domain"] = context["dataset_domain"]
        item["semantic_domain_label"] = context["dataset_domain_label"]
        item["semantic_mode"] = context["request_mode"]
        item["semantic_mode_label"] = context["request_mode_label"]
        item["semantic_focus"] = context["focus_label"]
        item["semantic_subject"] = context["semantic_subject"]

    return plan_items


def mark_plan_for_tool_start(
    plan_items: list[dict[str, str]], tool_name: str, tool_args: dict[str, Any]
) -> tuple[list[dict[str, str]], str]:
    context = extract_plan_context(plan_items)
    subject = context.get("semantic_subject") or _subject_from_tool_args(tool_name, tool_args)

    _mark_status(plan_items, "understand", "completed")

    if tool_name == "metadata_query":
        table_name = tool_args.get("table_name")
        table_subject = _subject_from_table_name(table_name) or subject
        detail = (
            f"正在查看{table_subject}表 `{table_name}` 的字段、类型和口径。"
            if table_name
            else f"正在查看{table_subject}相关表的字段、类型和口径。"
        )
        _mark_status(plan_items, "inspect", "in_progress", detail)
        _mark_status(plan_items, "query", "pending")
        return plan_items, f"先确认{table_subject}表结构，再决定后续查询口径。"

    if tool_name == "sql_executor":
        sql = str(tool_args.get("query", ""))
        if _get_item(plan_items, "inspect")["status"] == "pending":
            _mark_status(plan_items, "inspect", "skipped", "字段范围已经足够清楚，直接查询更高效。")
        _mark_status(plan_items, "query", "in_progress", describe_sql_purpose(sql, plan_items))
        return plan_items, f"开始提取{subject}数据，验证当前问题中的关键事实。"

    if tool_name == "chart_generator":
        _mark_status(plan_items, "query", "completed")
        _mark_status(plan_items, "analyze", "completed")
        _mark_status(plan_items, "chart", "in_progress", f"正在把{subject}结果整理成图表配置。")
        return plan_items, f"数据已经足够，补一层{subject}图表让结论更直观。"

    if tool_name == "knowledge_search":
        if _get_item(plan_items, "query")["status"] == "pending":
            _mark_status(plan_items, "query", "skipped", "这一轮先补规则背景，不直接查事实数据。")
        _mark_status(plan_items, "analyze", "in_progress", f"正在补充{subject}规则或口径依据。")
        return plan_items, f"先补{subject}规则依据，再把业务现象解释清楚。"

    return plan_items, "执行新的工具步骤，继续补全分析证据。"


def mark_plan_for_tool_result(
    plan_items: list[dict[str, str]], tool_name: str, result: Any
) -> tuple[list[dict[str, str]], str]:
    context = extract_plan_context(plan_items)
    subject = context.get("semantic_subject") or "业务"

    if tool_name == "metadata_query":
        _mark_status(plan_items, "inspect", "completed", summarize_tool_result(tool_name, result, plan_items))
        _mark_status(plan_items, "query", "pending", f"{subject}表结构已确认，可继续做数据查询。")
        return plan_items, f"{subject}表结构已确认，后续可以更精确地取数。"

    if tool_name == "sql_executor":
        _mark_status(plan_items, "query", "completed", summarize_tool_result(tool_name, result, plan_items))
        _mark_status(plan_items, "analyze", "in_progress", f"已拿到{subject}关键数据，正在归纳趋势与差异。")
        return plan_items, f"{subject}关键数据已经返回，开始整理分析结论。"

    if tool_name == "chart_generator":
        _mark_status(plan_items, "chart", "completed", summarize_tool_result(tool_name, result, plan_items))
        _mark_status(plan_items, "answer", "in_progress", f"{subject}图表已准备好，正在组织最终回答。")
        return plan_items, f"{subject}图表已经生成，接下来收束成最终结论。"

    if tool_name == "knowledge_search":
        _mark_status(plan_items, "analyze", "in_progress", summarize_tool_result(tool_name, result, plan_items))
        return plan_items, f"{subject}规则依据已经补齐，继续解释业务现象。"

    return plan_items, "分析计划已根据最新结果同步更新。"


def mark_plan_for_final_answer(plan_items: list[dict[str, str]]) -> tuple[list[dict[str, str]], str]:
    context = extract_plan_context(plan_items)
    subject = context.get("semantic_subject") or "业务"

    _mark_status(plan_items, "understand", "completed")

    for key in ("inspect", "query", "chart"):
        item = _get_item(plan_items, key)
        if item["status"] == "pending":
            _mark_status(plan_items, key, "skipped", f"本轮{subject}问题不需要这一步。")
        elif item["status"] == "in_progress":
            _mark_status(plan_items, key, "completed")

    analyze_item = _get_item(plan_items, "analyze")
    if analyze_item["status"] in {"pending", "in_progress"}:
        _mark_status(plan_items, "analyze", "completed", f"{subject}分析已经完成，准备交付结论。")

    _mark_status(plan_items, "answer", "completed", "最终回答已经生成。")
    return plan_items, "计划执行完成，准备输出最终结论。"


def build_plan_metadata(
    plan_items: list[dict[str, str]], title: str, change_reason: str | None = None
) -> dict[str, Any]:
    return {
        "plan_title": title,
        "plan_items": [dict(item) for item in plan_items],
        "change_reason": change_reason or "",
        "semantic_context": extract_plan_context(plan_items),
    }


def summarize_tool_action(
    tool_name: str, tool_args: dict[str, Any], plan_items: list[dict[str, str]] | None = None
) -> dict[str, Any]:
    context = extract_plan_context(plan_items)
    subject = context.get("semantic_subject") or _subject_from_tool_args(tool_name, tool_args)
    tool_info = _tool_catalog_entry(tool_name, subject)

    metadata: dict[str, Any] = {
        "tool_name": tool_name,
        "tool_label": tool_info["label"],
        "tool_summary": tool_info["summary"],
        "tool_input": tool_args,
        "tool_input_summary": summarize_tool_input(tool_name, tool_args, plan_items),
        "semantic_domain": context.get("dataset_domain", ""),
        "semantic_subject": subject,
        "semantic_mode": context.get("request_mode", ""),
    }

    sql_query = tool_args.get("query") if isinstance(tool_args, dict) else None
    if sql_query:
        metadata["sql_preview"] = sql_query
        metadata["sql_summary"] = describe_sql_purpose(sql_query, plan_items)

    return metadata


def summarize_observation_metadata(
    tool_name: str,
    result: Any,
    duration_ms: int,
    plan_items: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    context = extract_plan_context(plan_items)
    subject = context.get("semantic_subject") or "业务"
    metadata: dict[str, Any] = {
        "tool_name": tool_name,
        "tool_label": _tool_catalog_entry(tool_name, subject)["label"],
        "duration_ms": duration_ms,
        "result_summary": summarize_tool_result(tool_name, result, plan_items),
        "semantic_domain": context.get("dataset_domain", ""),
        "semantic_subject": subject,
    }

    if isinstance(result, dict):
        if tool_name == "sql_executor" and result.get("sql"):
            metadata["sql"] = result["sql"]
            metadata["sql_summary"] = describe_sql_purpose(result["sql"], plan_items)
        if tool_name == "chart_generator" and result.get("chart_config"):
            metadata["chart_config"] = result["chart_config"]
        if "columns" in result and "rows" in result:
            metadata["table_data"] = {
                "columns": result["columns"],
                "rows": result["rows"][:20],
            }

    return metadata


def summarize_tool_input(
    tool_name: str,
    tool_args: dict[str, Any],
    plan_items: list[dict[str, str]] | None = None,
) -> str:
    context = extract_plan_context(plan_items)
    subject = context.get("semantic_subject") or _subject_from_tool_args(tool_name, tool_args)

    if tool_name == "metadata_query":
        table_name = tool_args.get("table_name")
        if table_name:
            return f"准备查看{_subject_from_table_name(table_name) or subject}表 `{table_name}` 的结构。"
        return f"准备查看{subject}相关表结构。"

    if tool_name == "sql_executor":
        return describe_sql_purpose(tool_args.get("query", ""), plan_items)

    if tool_name == "chart_generator":
        chart_type = tool_args.get("chart_type", "bar")
        title = tool_args.get("title") or f"{subject}分析图"
        return f"准备生成一个 `{chart_type}` 图，标题是“{title}”。"

    if tool_name == "knowledge_search":
        query = tool_args.get("query") or ""
        return f"准备检索与“{query}”相关的{subject}规则或口径。"

    return "准备执行一个辅助分析动作。"


def summarize_tool_result(
    tool_name: str,
    result: Any,
    plan_items: list[dict[str, str]] | None = None,
) -> str:
    context = extract_plan_context(plan_items)
    subject = context.get("semantic_subject") or "业务"

    if isinstance(result, dict) and result.get("error"):
        return f"工具执行失败：{result['error']}"

    if tool_name == "metadata_query" and isinstance(result, dict):
        if result.get("tables") is not None:
            count = result.get("count", len(result.get("tables", [])))
            return f"已获取{subject}相关表清单，共 {count} 张表。"
        if result.get("columns") is not None:
            table_name = result.get("table_name", "目标表")
            return f"已确认 `{table_name}` 的字段信息，共 {len(result.get('columns', []))} 个字段。"

    if tool_name == "sql_executor" and isinstance(result, dict):
        row_count = result.get("row_count", 0)
        if row_count == 0:
            return f"SQL 已执行，但当前筛选条件下没有返回{subject}数据。"
        return f"SQL 已返回 {row_count} 行{subject}结果，可继续分析。"

    if tool_name == "chart_generator" and isinstance(result, dict):
        chart_type = result.get("chart_type", "图表")
        return f"已生成 `{chart_type}` 图表配置，可以直接渲染{subject}结果。"

    if tool_name == "knowledge_search" and isinstance(result, list):
        return f"已检索到 {len(result)} 条{subject}规则依据，可用于补充说明。"

    return "步骤已完成，结果已经回到分析流程。"


def describe_sql_purpose(
    query: str, plan_items: list[dict[str, str]] | None = None
) -> str:
    if not query:
        return "准备执行 SQL 查询。"

    context = extract_plan_context(plan_items)
    subject = context.get("semantic_subject") or _subject_from_sql(query) or "业务"

    normalized = re.sub(r"\s+", " ", query.strip())
    upper_query = normalized.upper()
    tables = _extract_tables(normalized)
    table_desc = "、".join(f"`{name}`" for name in tables[:3]) if tables else "目标表"

    if "COUNT(" in upper_query and "GROUP BY" not in upper_query:
        action = f"统计{subject}数据"
    elif any(keyword in upper_query for keyword in ("SUM(", "AVG(", "MAX(", "MIN(")):
        action = f"汇总{subject}数据"
    elif "GROUP BY" in upper_query and "ORDER BY" in upper_query:
        action = f"生成{subject}排行"
    elif "GROUP BY" in upper_query:
        action = f"按维度汇总{subject}数据"
    elif "ORDER BY" in upper_query and "LIMIT" in upper_query:
        action = f"生成{subject}排行"
    else:
        action = f"查询{subject}数据"

    filters: list[str] = []
    periods = re.findall(r"\b20\d{2}-\d{2}\b", normalized)
    if periods:
        filters.append("时间范围 " + "、".join(periods[:2]))
    if "LIMIT" in upper_query:
        limit_match = re.search(r"\bLIMIT\s+(\d+)", upper_query)
        if limit_match:
            filters.append(f"最多返回 {limit_match.group(1)} 行")

    filter_desc = f"，过滤条件包括 {', '.join(filters)}" if filters else ""
    return f"这条 SQL 正在{action}，涉及表 {table_desc}{filter_desc}。"


def _tool_catalog_entry(tool_name: str, subject: str) -> dict[str, str]:
    catalog = {
        "sql_executor": {
            "label": f"查询{subject}数据" if subject != "业务" else "查询业务数据",
            "summary": f"执行只读 SQL，从{subject}数据中提取分析所需结果。",
        },
        "metadata_query": {
            "label": f"查看{subject}表结构" if subject != "业务" else "查看表结构",
            "summary": f"查看{subject}相关表的字段、类型和口径。",
        },
        "chart_generator": {
            "label": f"生成{subject}图表" if subject != "业务" else "生成结果图表",
            "summary": f"把查询结果整理成可直接渲染的图表配置。",
        },
        "knowledge_search": {
            "label": f"检索{subject}规则" if subject != "业务" else "检索业务规则",
            "summary": f"补充{subject}相关的规则、口径或解释依据。",
        },
    }
    return catalog.get(
        tool_name,
        {"label": tool_name, "summary": "执行一个辅助分析动作。"},
    )


def _normalize_semantic_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword.lower() in text.lower() for keyword in keywords)


def _detect_domain(text: str, table_names: list[str]) -> str:
    scored = {
        "tax": sum(1 for keyword in _TAX_KEYWORDS if keyword.lower() in text.lower()),
        "accounting": sum(1 for keyword in _ACCOUNTING_KEYWORDS if keyword.lower() in text.lower()),
    }

    for table_name in table_names:
        table_text = table_name.lower()
        if _contains_any(table_text, _TAX_KEYWORDS):
            scored["tax"] += 2
        if _contains_any(table_text, _ACCOUNTING_KEYWORDS):
            scored["accounting"] += 2

    if scored["tax"] > scored["accounting"] and scored["tax"] > 0:
        return "tax"
    if scored["accounting"] > scored["tax"] and scored["accounting"] > 0:
        return "accounting"
    return "general"


def _detect_request_mode(text: str, tool_name: str | None) -> str:
    lowered = text.lower()
    if tool_name == "metadata_query" or _contains_any(lowered, _SCHEMA_KEYWORDS):
        return "schema"
    if tool_name == "chart_generator" or _contains_any(lowered, _CHART_KEYWORDS):
        return "chart"
    if tool_name == "knowledge_search":
        return "knowledge"
    if _contains_any(lowered, ("分析", "对比", "差异", "异常", "原因", "同比", "环比", "结论", "报表")):
        return "analysis"
    return "query"


def _mode_label(mode: str) -> str:
    return {
        "schema": "表结构",
        "chart": "图表",
        "knowledge": "规则",
        "analysis": "分析",
        "query": "查询",
    }.get(mode, "查询")


def _domain_subject(domain: str) -> str:
    return {
        "tax": "税务",
        "accounting": "账务",
        "general": "业务",
    }.get(domain, "业务")


def _build_focus_label(domain: str, mode: str) -> str:
    subject = _domain_subject(domain)
    if mode == "schema":
        return f"查看{subject}表结构" if subject != "业务" else "查看表结构"
    if mode == "chart":
        return f"查看{subject}数据并生成图表" if subject != "业务" else "生成图表"
    if mode == "knowledge":
        return f"检索{subject}规则" if subject != "业务" else "检索业务规则"
    if mode == "analysis":
        return f"分析{subject}数据" if subject != "业务" else "分析业务数据"
    return f"查询{subject}数据" if subject != "业务" else "查询业务数据"


def _collect_table_names(tool_args: dict[str, Any] | None) -> list[str]:
    if not isinstance(tool_args, dict):
        return []

    raw_tables = tool_args.get("tables") or tool_args.get("table_names")
    tables: list[str] = []
    if isinstance(raw_tables, list):
        for name in raw_tables:
            if isinstance(name, str) and name and name not in tables:
                tables.append(name)

    table_name = tool_args.get("table_name") or tool_args.get("table")
    if isinstance(table_name, str) and table_name and table_name not in tables:
        tables.append(table_name)

    sql = tool_args.get("query")
    if isinstance(sql, str):
        for name in _extract_tables(sql):
            if name not in tables:
                tables.append(name)

    return tables


def _subject_from_table_name(table_name: Any) -> str:
    if not isinstance(table_name, str) or not table_name:
        return ""
    table_text = table_name.lower()
    if _contains_any(table_text, _TAX_KEYWORDS):
        return "税务"
    if _contains_any(table_text, _ACCOUNTING_KEYWORDS):
        return "账务"
    return ""


def _subject_from_sql(query: str) -> str:
    tables = _extract_tables(query)
    for table_name in tables:
        subject = _subject_from_table_name(table_name)
        if subject:
            return subject

    lowered = query.lower()
    if _contains_any(lowered, _TAX_KEYWORDS):
        return "税务"
    if _contains_any(lowered, _ACCOUNTING_KEYWORDS):
        return "账务"
    return ""


def _subject_from_tool_args(tool_name: str, tool_args: dict[str, Any]) -> str:
    if tool_name == "metadata_query":
        subject = _subject_from_table_name(tool_args.get("table_name"))
        if subject:
            return subject
    if tool_name == "sql_executor":
        subject = _subject_from_sql(str(tool_args.get("query", "")))
        if subject:
            return subject
    if tool_name == "chart_generator":
        title = str(tool_args.get("title", ""))
        if _contains_any(title, _TAX_KEYWORDS):
            return "税务"
        if _contains_any(title, _ACCOUNTING_KEYWORDS):
            return "账务"
    if tool_name == "knowledge_search":
        query = str(tool_args.get("query", ""))
        if _contains_any(query, _TAX_KEYWORDS):
            return "税务"
        if _contains_any(query, _ACCOUNTING_KEYWORDS):
            return "账务"
    return "业务"


def _extract_tables(query: str) -> list[str]:
    matches = re.findall(r"\b(?:FROM|JOIN)\s+([A-Za-z_][A-Za-z0-9_]*)", query, flags=re.IGNORECASE)
    tables: list[str] = []
    for name in matches:
        if name not in tables:
            tables.append(name)
    return tables
