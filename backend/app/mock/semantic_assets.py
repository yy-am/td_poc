"""Semantic asset catalog used by seeds, mock generation, and management APIs."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.semantic import SysSemanticModel
from app.semantic.catalog import infer_model_type_from_kind

LEGACY_MODEL_NAMES = {
    "vat_declaration",
    "vat_invoice_summary",
    "cit_quarterly",
    "cit_annual",
    "cit_adjustments",
    "other_taxes",
    "risk_indicators",
    "income_statement",
    "balance_sheet",
    "journal_entries",
    "general_ledger",
    "tax_payable_detail",
    "depreciation",
    "revenue_comparison",
    "tax_burden_analysis",
    "adjustment_tracking",
    "cross_check",
    "enterprise_master",
    "enterprise_tax_overview",
    "reconciliation_dashboard",
}


def _dimension(
    name: str,
    label: str,
    *,
    column: str | None = None,
    source: str | None = None,
    dtype: str = "string",
    expr: str | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {"name": name, "label": label, "type": dtype}
    if expr:
        item["expr"] = expr
    elif column:
        item["column"] = column
    if source:
        item["source"] = source
    return item


def _metric(
    name: str,
    label: str,
    *,
    column: str | None = None,
    source: str | None = None,
    agg: str | None = None,
    expr: str | None = None,
    fmt: str | None = None,
    depends_on: list[str] | None = None,
    metric_time: str | None = None,
    semantic_role: str | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {"name": name, "label": label}
    if expr:
        item["expr"] = expr
    elif column:
        item["column"] = column
    if source:
        item["source"] = source
    if agg:
        item["agg"] = agg
    if fmt:
        item["format"] = fmt
    if depends_on:
        item["depends_on"] = depends_on
    if metric_time:
        item["metric_time"] = metric_time
    item["semantic_role"] = semantic_role or ("composite" if depends_on else "atomic")
    return item


def _entity(
    *,
    display_field: str,
    primary_key: str,
    resolver_model: str,
    input_fields: list[str],
    output_field: str | None = None,
) -> dict[str, Any]:
    return {
        "display_field": display_field,
        "primary_key": primary_key,
        "resolver": {
            "model": resolver_model,
            "input_fields": input_fields,
            "output_field": output_field or primary_key,
        },
    }


def _time(field: str, grain: str, available_grains: list[str]) -> dict[str, Any]:
    return {"field": field, "grain": grain, "available_grains": available_grains}


def _time_with_roles(
    field: str,
    grain: str,
    available_grains: list[str],
    *,
    default_role: str,
    roles: dict[str, Any],
    date_fields: dict[str, str] | None = None,
) -> dict[str, Any]:
    payload = _time(field, grain, available_grains)
    payload["default_role"] = default_role
    payload["roles"] = roles
    if date_fields:
        payload["date_fields"] = date_fields
    return payload


def _build_metric_lineage(metrics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lineage: list[dict[str, Any]] = []
    for metric in metrics:
        expr = str(metric.get("expr") or "").strip()
        if not expr and metric.get("column"):
            agg = str(metric.get("agg") or "").strip()
            expr = f"{agg.upper()}({metric['column']})" if agg else str(metric["column"])
        lineage.append({
            "metric_name": metric.get("name"),
            "label": metric.get("label"),
            "expression": expr,
            "depends_on": list(metric.get("depends_on") or []),
            "metric_time": metric.get("metric_time"),
            "semantic_role": metric.get("semantic_role") or "atomic",
        })
    return lineage


def _build_relationship_graph(
    sources: list[dict[str, Any]],
    joins: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    alias_map = {
        str(source.get("alias") or ""): str(source.get("table") or source.get("model") or source.get("alias") or "")
        for source in sources
    }
    graph: list[dict[str, Any]] = []
    for join in joins or []:
        left = str(join.get("left") or "")
        right = str(join.get("right") or "")
        if "." not in left or "." not in right:
            continue
        left_alias = left.split(".", 1)[0]
        right_alias = right.split(".", 1)[0]
        graph.append({
            "source": alias_map.get(left_alias, left_alias),
            "target": alias_map.get(right_alias, right_alias),
            "join_type": str(join.get("type") or "left"),
            "join_on": f"{left} = {right}",
            "weight": 1,
        })
    return graph


def _default_materialization_policy(kind: str, source_table: str) -> dict[str, Any]:
    if kind == "composite_analysis":
        return {
            "mode": "prefer_semantic_asset",
            "primary_source": source_table,
            "cacheable": True,
        }
    if kind == "atomic_fact":
        return {
            "mode": "prefer_source_table",
            "primary_source": source_table,
            "cacheable": True,
        }
    return {
        "mode": "dimension_lookup",
        "primary_source": source_table,
        "cacheable": True,
    }


def _default_query_hints(
    kind: str,
    analysis_patterns: list[str] | None,
    detail_fields: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    return {
        "preferred_lane": "metric" if kind == "composite_analysis" else "detail",
        "supports_drilldown": bool(detail_fields),
        "recommended_patterns": list(analysis_patterns or [])[:4],
    }


def _model(
    *,
    name: str,
    label: str,
    description: str,
    kind: str,
    domain: str,
    grain: str,
    source_table: str,
    sources: list[dict[str, Any]],
    dimensions: list[dict[str, Any]],
    metrics: list[dict[str, Any]],
    joins: list[dict[str, Any]] | None = None,
    entities: dict[str, Any] | None = None,
    time: dict[str, Any] | None = None,
    business_terms: list[str] | None = None,
    analysis_patterns: list[str] | None = None,
    evidence_requirements: list[str] | None = None,
    intent_aliases: list[str] | None = None,
    fallback_policy: str = "fallback_to_sql",
    entry_enabled: bool = True,
    default_limit: int = 200,
    detail_fields: list[dict[str, Any]] | None = None,
    relationship_graph: list[dict[str, Any]] | None = None,
    metric_lineage: list[dict[str, Any]] | None = None,
    materialization_policy: dict[str, Any] | None = None,
    query_hints: dict[str, Any] | None = None,
) -> dict[str, Any]:
    detail_fields = deepcopy(detail_fields) if detail_fields else deepcopy(dimensions[: min(len(dimensions), 8)])
    relationship_graph = relationship_graph or _build_relationship_graph(sources, joins or [])
    metric_lineage = metric_lineage or _build_metric_lineage(metrics)
    materialization_policy = materialization_policy or _default_materialization_policy(kind, source_table)
    query_hints = query_hints or _default_query_hints(kind, analysis_patterns, detail_fields)
    definition = {
        "name": name,
        "label": label,
        "description": description,
        "kind": kind,
        "domain": domain,
        "grain": grain,
        "entry_enabled": entry_enabled,
        "sources": sources,
        "joins": joins or [],
        "dimensions": dimensions,
        "metrics": metrics,
        "entities": entities or {},
        "time": time or {},
        "business_terms": business_terms or [],
        "intent_aliases": intent_aliases or [],
        "analysis_patterns": analysis_patterns or [],
        "evidence_requirements": evidence_requirements or [],
        "fallback_policy": fallback_policy,
        "default_limit": default_limit,
        "detail_fields": detail_fields,
        "relationship_graph": relationship_graph,
        "metric_lineage": metric_lineage,
        "materialization_policy": materialization_policy,
        "query_hints": query_hints,
    }
    return {
        "name": name,
        "label": label,
        "description": description,
        "source_table": source_table,
        "model_type": infer_model_type_from_kind(kind),
        "yaml_definition": yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        "status": "active",
    }


def _enterprise_dimensions(source: str = "e") -> list[dict[str, Any]]:
    return [
        _dimension("taxpayer_id", "纳税人识别号", column="taxpayer_id", source=source),
        _dimension("enterprise_name", "企业名称", column="enterprise_name", source=source),
        _dimension("industry_code", "行业代码", column="industry_code", source=source),
        _dimension("industry_name", "行业名称", column="industry_name", source=source),
        _dimension("registration_type", "纳税人类型", column="registration_type", source=source),
        _dimension("tax_authority", "主管税务机关", column="tax_authority", source=source),
        _dimension("legal_representative", "法定代表人", column="legal_representative", source=source),
        _dimension("status", "企业状态", column="status", source=source),
    ]


def _enterprise_entity() -> dict[str, Any]:
    return {
        "enterprise": _entity(
            display_field="enterprise_name",
            primary_key="taxpayer_id",
            resolver_model="dim_enterprise",
            input_fields=["enterprise_name", "taxpayer_id"],
        )
    }


def _industry_entity() -> dict[str, Any]:
    return {
        "industry": _entity(
            display_field="industry_name",
            primary_key="industry_code",
            resolver_model="dim_industry",
            input_fields=["industry_name", "industry_code"],
        )
    }


def _tax_type_entity() -> dict[str, Any]:
    return {
        "tax_type": _entity(
            display_field="tax_name",
            primary_key="tax_code",
            resolver_model="dim_tax_type",
            input_fields=["tax_name", "tax_code"],
        )
    }


def _shared_fact_entities() -> dict[str, Any]:
    entities = deepcopy(_enterprise_entity())
    entities.update(_industry_entity())
    return entities


def build_semantic_model_records() -> list[dict[str, Any]]:
    shared_entities = _shared_fact_entities()
    enterprise_only_entities = _enterprise_entity()

    records: list[dict[str, Any]] = [
        _model(
            name="dim_enterprise",
            label="企业主数据",
            description="统一管理企业实体、行业和主管税务机关，是企业名称解析为纳税人识别号的入口模型。",
            kind="entity_dimension",
            domain="core",
            grain="enterprise",
            source_table="enterprise_info",
            sources=[{"table": "enterprise_info", "alias": "e"}],
            dimensions=_enterprise_dimensions("e"),
            metrics=[_metric("enterprise_count", "企业数量", expr="COUNT(*)")],
            entities=_enterprise_entity(),
            business_terms=["企业名称", "纳税人识别号", "行业", "主管税务机关"],
            intent_aliases=["企业档案", "企业主档", "企业主体"],
            analysis_patterns=["实体解析", "主体筛选", "行业归类"],
            evidence_requirements=["返回企业名称与纳税人识别号映射", "需要时补充行业和主管税务机关"],
        ),
        _model(
            name="dim_industry",
            label="行业字典",
            description="统一管理行业代码、行业名称和行业平均税负基准，用于行业映射与行业比较。",
            kind="entity_dimension",
            domain="core",
            grain="industry",
            source_table="dict_industry",
            sources=[{"table": "dict_industry", "alias": "di"}],
            dimensions=[
                _dimension("industry_code", "行业代码", column="industry_code", source="di"),
                _dimension("industry_name", "行业名称", column="industry_name", source="di"),
                _dimension("parent_code", "上级行业代码", column="parent_code", source="di"),
            ],
            metrics=[
                _metric("avg_vat_burden", "行业平均增值税税负率", column="avg_vat_burden", source="di", agg="avg", fmt="percent"),
                _metric("avg_cit_rate", "行业平均所得税税率", column="avg_cit_rate", source="di", agg="avg", fmt="percent"),
            ],
            entities=_industry_entity(),
            business_terms=["行业代码", "行业名称", "行业平均税负"],
            analysis_patterns=["行业映射", "行业基准对比"],
            evidence_requirements=["返回行业代码与行业名称映射", "涉及行业比较时返回行业平均税负"],
        ),
        _model(
            name="dim_tax_type",
            label="税种字典",
            description="统一管理税种编码、税种名称和标准税率，用于税种标准化和税种筛选。",
            kind="entity_dimension",
            domain="core",
            grain="tax_type",
            source_table="dict_tax_type",
            sources=[{"table": "dict_tax_type", "alias": "dt"}],
            dimensions=[
                _dimension("tax_code", "税种编码", column="tax_code", source="dt"),
                _dimension("tax_name", "税种名称", column="tax_name", source="dt"),
                _dimension("standard_rate", "标准税率", column="standard_rate", source="dt"),
            ],
            metrics=[_metric("tax_type_count", "税种数量", expr="COUNT(*)")],
            entities=_tax_type_entity(),
            business_terms=["税种", "税率", "税种编码"],
            analysis_patterns=["税种标准化", "税种过滤"],
            evidence_requirements=["返回税种编码与税种名称映射"],
        ),
        _model(
            name="dim_account",
            label="会计科目字典",
            description="统一管理会计科目编码、层级、余额方向和科目类别，用于总账与凭证语义映射。",
            kind="entity_dimension",
            domain="accounting",
            grain="account",
            source_table="acct_chart_of_accounts",
            sources=[{"table": "acct_chart_of_accounts", "alias": "coa"}],
            dimensions=[
                _dimension("account_code", "科目编码", column="account_code", source="coa"),
                _dimension("account_name", "科目名称", column="account_name", source="coa"),
                _dimension("account_type", "科目类别", column="account_type", source="coa"),
                _dimension("parent_code", "上级科目编码", column="parent_code", source="coa"),
                _dimension("level", "科目层级", column="level", source="coa", dtype="number"),
                _dimension("direction", "余额方向", column="direction", source="coa"),
            ],
            metrics=[_metric("account_count", "科目数量", expr="COUNT(*)")],
            business_terms=["科目编码", "科目名称", "余额方向"],
            analysis_patterns=["科目映射", "总账科目过滤", "凭证科目钻取"],
            evidence_requirements=["返回科目编码与科目名称", "涉及余额时明确借贷方向"],
        ),
    ]

    records.extend(
        [
            _model(
                name="fact_vat_declaration",
                label="增值税申报事实",
                description="按企业和月份沉淀的增值税申报事实，可用于销项税额、进项税额与应纳税额分析。",
                kind="atomic_fact",
                domain="tax",
                grain="enterprise_month",
                source_table="tax_vat_declaration",
                sources=[{"table": "tax_vat_declaration", "alias": "vd"}, {"table": "enterprise_info", "alias": "e"}],
                joins=[{"left": "vd.taxpayer_id", "right": "e.taxpayer_id", "type": "left"}],
                dimensions=[
                    _dimension("taxpayer_id", "纳税人识别号", column="taxpayer_id", source="vd"),
                    _dimension("tax_period", "税款所属期", column="tax_period", source="vd"),
                    _dimension("enterprise_name", "企业名称", column="enterprise_name", source="e"),
                    _dimension("industry_code", "行业代码", column="industry_code", source="e"),
                    _dimension("industry_name", "行业名称", column="industry_name", source="e"),
                ],
                metrics=[
                    _metric("total_sales_amount", "销售额合计", column="total_sales_amount", source="vd", agg="sum"),
                    _metric("taxable_sales_amount", "应税销售额", column="taxable_sales_amount", source="vd", agg="sum"),
                    _metric("exempt_sales_amount", "免税销售额", column="exempt_sales_amount", source="vd", agg="sum"),
                    _metric("output_tax_amount", "销项税额", column="output_tax_amount", source="vd", agg="sum"),
                    _metric("input_tax_amount", "进项税额", column="input_tax_amount", source="vd", agg="sum"),
                    _metric("input_tax_transferred_out", "进项税额转出", column="input_tax_transferred_out", source="vd", agg="sum"),
                    _metric("tax_payable", "应纳税额", column="tax_payable", source="vd", agg="sum"),
                ],
                entities=deepcopy(shared_entities),
                time=_time("tax_period", "month", ["month", "quarter", "year"]),
                business_terms=["增值税申报", "销项税额", "进项税额", "应纳税额"],
                analysis_patterns=["申报金额趋势", "税负测算", "企业申报对比"],
                evidence_requirements=["需要同时返回企业和税期", "涉及税负时给出销售额与税额"],
            ),
            _model(
                name="fact_vat_invoice_summary",
                label="增值税发票汇总事实",
                description="按企业、月份和发票类型统计发票份数、金额和税额，用于发票口径分析。",
                kind="atomic_fact",
                domain="tax",
                grain="enterprise_month_invoice_type",
                source_table="tax_vat_invoice_summary",
                sources=[{"table": "tax_vat_invoice_summary", "alias": "vi"}, {"table": "enterprise_info", "alias": "e"}],
                joins=[{"left": "vi.taxpayer_id", "right": "e.taxpayer_id", "type": "left"}],
                dimensions=[
                    _dimension("taxpayer_id", "纳税人识别号", column="taxpayer_id", source="vi"),
                    _dimension("tax_period", "税款所属期", column="tax_period", source="vi"),
                    _dimension("invoice_type", "发票类型", column="invoice_type", source="vi"),
                    _dimension("enterprise_name", "企业名称", column="enterprise_name", source="e"),
                ],
                metrics=[
                    _metric("invoice_count", "发票份数", column="invoice_count", source="vi", agg="sum"),
                    _metric("total_amount", "金额合计", column="total_amount", source="vi", agg="sum"),
                    _metric("total_tax", "税额合计", column="total_tax", source="vi", agg="sum"),
                    _metric("total_amount_with_tax", "价税合计", column="total_amount_with_tax", source="vi", agg="sum"),
                ],
                entities=deepcopy(enterprise_only_entities),
                time=_time("tax_period", "month", ["month", "quarter", "year"]),
                business_terms=["发票汇总", "专票", "普票", "电子票"],
                analysis_patterns=["发票结构分析", "发票金额趋势", "发票与申报对照"],
                evidence_requirements=["涉及发票分析时返回发票类型", "需要金额和税额配对展示"],
            ),
            _model(
                name="fact_cit_quarterly",
                label="企业所得税季度预缴事实",
                description="按企业和季度沉淀所得税预缴事实，用于收入、成本、利润和预缴税额分析。",
                kind="atomic_fact",
                domain="tax",
                grain="enterprise_quarter",
                source_table="tax_cit_quarterly",
                sources=[{"table": "tax_cit_quarterly", "alias": "cq"}, {"table": "enterprise_info", "alias": "e"}],
                joins=[{"left": "cq.taxpayer_id", "right": "e.taxpayer_id", "type": "left"}],
                dimensions=[
                    _dimension("taxpayer_id", "纳税人识别号", column="taxpayer_id", source="cq"),
                    _dimension("tax_year", "纳税年度", column="tax_year", source="cq", dtype="number"),
                    _dimension("quarter", "季度", column="quarter", source="cq", dtype="number"),
                    _dimension("enterprise_name", "企业名称", column="enterprise_name", source="e"),
                    _dimension("industry_name", "行业名称", column="industry_name", source="e"),
                ],
                metrics=[
                    _metric("revenue_total", "营业收入", column="revenue_total", source="cq", agg="sum"),
                    _metric("cost_total", "营业成本", column="cost_total", source="cq", agg="sum"),
                    _metric("profit_total", "利润总额", column="profit_total", source="cq", agg="sum"),
                    _metric("taxable_income", "应纳税所得额", column="taxable_income", source="cq", agg="sum"),
                    _metric("tax_payable", "应纳所得税额", column="tax_payable", source="cq", agg="sum"),
                    _metric("tax_prepaid", "已预缴税额", column="tax_prepaid", source="cq", agg="sum"),
                ],
                entities=deepcopy(shared_entities),
                time=_time("tax_year", "quarter", ["quarter", "year"]),
                business_terms=["季度预缴", "所得税", "利润总额", "应纳税所得额"],
                analysis_patterns=["季度利润分析", "季度预缴分析", "所得税口径对比"],
                evidence_requirements=["必须返回纳税年度和季度", "预缴分析需同时给出利润和税额"],
            ),
            _model(
                name="fact_cit_annual",
                label="企业所得税年度汇算事实",
                description="按企业和年度沉淀所得税汇算清缴结果，可用于税会差异和补退税分析。",
                kind="atomic_fact",
                domain="tax",
                grain="enterprise_year",
                source_table="tax_cit_annual",
                sources=[{"table": "tax_cit_annual", "alias": "ca"}, {"table": "enterprise_info", "alias": "e"}],
                joins=[{"left": "ca.taxpayer_id", "right": "e.taxpayer_id", "type": "left"}],
                dimensions=[
                    _dimension("taxpayer_id", "纳税人识别号", column="taxpayer_id", source="ca"),
                    _dimension("tax_year", "纳税年度", column="tax_year", source="ca", dtype="number"),
                    _dimension("enterprise_name", "企业名称", column="enterprise_name", source="e"),
                    _dimension("industry_name", "行业名称", column="industry_name", source="e"),
                ],
                metrics=[
                    _metric("accounting_profit", "会计利润", column="accounting_profit", source="ca", agg="sum"),
                    _metric("tax_adjustments_increase", "纳税调增", column="tax_adjustments_increase", source="ca", agg="sum"),
                    _metric("tax_adjustments_decrease", "纳税调减", column="tax_adjustments_decrease", source="ca", agg="sum"),
                    _metric("taxable_income", "应纳税所得额", column="taxable_income", source="ca", agg="sum"),
                    _metric("tax_amount", "应纳所得税额", column="tax_amount", source="ca", agg="sum"),
                    _metric("tax_prepaid", "已预缴税额", column="tax_prepaid", source="ca", agg="sum"),
                    _metric("tax_refund_or_due", "应退补税额", column="tax_refund_or_due", source="ca", agg="sum"),
                ],
                entities=deepcopy(shared_entities),
                time=_time("tax_year", "year", ["year"]),
                business_terms=["年度汇算", "纳税调增", "纳税调减", "补退税"],
                analysis_patterns=["年度汇算分析", "税会差异分析", "补退税分析"],
                evidence_requirements=["必须返回年度口径", "补退税结论需要同时展示预缴与应纳税额"],
            ),
        ]
    )

    records.extend(
        [
            _model(
                name="fact_balance_sheet",
                label="资产负债表事实",
                description="按企业和月份沉淀资产负债表关键科目，用于资产、负债和权益结构分析。",
                kind="atomic_fact",
                domain="accounting",
                grain="enterprise_month",
                source_table="acct_balance_sheet",
                sources=[{"table": "acct_balance_sheet", "alias": "bs"}, {"table": "enterprise_info", "alias": "e"}],
                joins=[{"left": "bs.taxpayer_id", "right": "e.taxpayer_id", "type": "left"}],
                dimensions=[
                    _dimension("taxpayer_id", "纳税人识别号", column="taxpayer_id", source="bs"),
                    _dimension("period", "会计期间", column="period", source="bs"),
                    _dimension("enterprise_name", "企业名称", column="enterprise_name", source="e"),
                    _dimension("industry_name", "行业名称", column="industry_name", source="e"),
                ],
                metrics=[
                    _metric("cash", "货币资金", column="cash", source="bs", agg="sum"),
                    _metric("receivables", "应收账款", column="receivables", source="bs", agg="sum"),
                    _metric("inventory", "存货", column="inventory", source="bs", agg="sum"),
                    _metric("fixed_assets", "固定资产", column="fixed_assets", source="bs", agg="sum"),
                    _metric("total_assets", "资产合计", column="total_assets", source="bs", agg="sum"),
                    _metric("payables", "应付账款", column="payables", source="bs", agg="sum"),
                    _metric("tax_payable_bs", "应交税费", column="tax_payable_bs", source="bs", agg="sum"),
                    _metric("total_liabilities", "负债合计", column="total_liabilities", source="bs", agg="sum"),
                    _metric("total_equity", "所有者权益合计", column="total_equity", source="bs", agg="sum"),
                ],
                entities=deepcopy(shared_entities),
                time=_time("period", "month", ["month", "quarter", "year"]),
                business_terms=["资产负债表", "资产合计", "负债合计", "所有者权益"],
                analysis_patterns=["资产结构分析", "负债变化分析", "资产负债率分析"],
                evidence_requirements=["资产负债结论需同时展示资产和负债", "结构分析建议附期间维度"],
            ),
            _model(
                name="fact_tax_payable_detail",
                label="应交税费明细事实",
                description="按企业、月份和税种沉淀应交税费明细，用于计提、缴纳和期末余额分析。",
                kind="atomic_fact",
                domain="accounting",
                grain="enterprise_month_tax_type",
                source_table="acct_tax_payable_detail",
                sources=[{"table": "acct_tax_payable_detail", "alias": "tp"}, {"table": "enterprise_info", "alias": "e"}],
                joins=[{"left": "tp.taxpayer_id", "right": "e.taxpayer_id", "type": "left"}],
                dimensions=[
                    _dimension("taxpayer_id", "纳税人识别号", column="taxpayer_id", source="tp"),
                    _dimension("period", "会计期间", column="period", source="tp"),
                    _dimension("tax_type", "税种", column="tax_type", source="tp"),
                    _dimension("enterprise_name", "企业名称", column="enterprise_name", source="e"),
                ],
                metrics=[
                    _metric("opening_balance", "期初余额", column="opening_balance", source="tp", agg="sum"),
                    _metric("accrued_amount", "本期计提", column="accrued_amount", source="tp", agg="sum"),
                    _metric("paid_amount", "本期缴纳", column="paid_amount", source="tp", agg="sum"),
                    _metric("closing_balance", "期末余额", column="closing_balance", source="tp", agg="sum"),
                ],
                entities=deepcopy(enterprise_only_entities),
                time=_time("period", "month", ["month", "quarter", "year"]),
                business_terms=["应交税费", "本期计提", "本期缴纳", "期末余额"],
                analysis_patterns=["税费余额分析", "计提缴纳对比"],
                evidence_requirements=["税费结论需要展示计提和缴纳", "涉及税种时返回税种维度"],
            ),
            _model(
                name="fact_depreciation_schedule",
                label="折旧台账事实",
                description="按企业和资产沉淀会计与税法折旧差异，用于暂时性差异分析。",
                kind="atomic_fact",
                domain="accounting",
                grain="enterprise_asset",
                source_table="acct_depreciation_schedule",
                sources=[{"table": "acct_depreciation_schedule", "alias": "ds"}, {"table": "enterprise_info", "alias": "e"}],
                joins=[{"left": "ds.taxpayer_id", "right": "e.taxpayer_id", "type": "left"}],
                dimensions=[
                    _dimension("taxpayer_id", "纳税人识别号", column="taxpayer_id", source="ds"),
                    _dimension("asset_id", "资产编号", column="asset_id", source="ds"),
                    _dimension("asset_name", "资产名称", column="asset_name", source="ds"),
                    _dimension("category", "资产类别", column="category", source="ds"),
                    _dimension("acct_method", "会计折旧方法", column="acct_method", source="ds"),
                    _dimension("tax_method", "税法折旧方法", column="tax_method", source="ds"),
                    _dimension("enterprise_name", "企业名称", column="enterprise_name", source="e"),
                ],
                metrics=[
                    _metric("original_value", "原值", column="original_value", source="ds", agg="sum"),
                    _metric("acct_depreciation_monthly", "会计月折旧额", column="acct_depreciation_monthly", source="ds", agg="sum"),
                    _metric("tax_depreciation_monthly", "税法月折旧额", column="tax_depreciation_monthly", source="ds", agg="sum"),
                    _metric("difference_monthly", "月差异额", column="difference_monthly", source="ds", agg="sum"),
                ],
                entities=deepcopy(enterprise_only_entities),
                business_terms=["折旧台账", "会计折旧", "税法折旧", "月差异额"],
                analysis_patterns=["折旧差异分析", "资产类别对比"],
                evidence_requirements=["差异结论需展示会计与税法两套金额", "需要返回资产类别或资产名称"],
            ),
            _model(
                name="fact_general_ledger",
                label="总账余额事实",
                description="按企业、期间和科目沉淀总账余额，用于科目余额和发生额分析。",
                kind="atomic_fact",
                domain="accounting",
                grain="enterprise_month_account",
                source_table="acct_general_ledger",
                sources=[
                    {"table": "acct_general_ledger", "alias": "gl"},
                    {"table": "enterprise_info", "alias": "e"},
                    {"table": "acct_chart_of_accounts", "alias": "coa"},
                ],
                joins=[
                    {"left": "gl.taxpayer_id", "right": "e.taxpayer_id", "type": "left"},
                    {"left": "gl.account_code", "right": "coa.account_code", "type": "left"},
                ],
                dimensions=[
                    _dimension("taxpayer_id", "纳税人识别号", column="taxpayer_id", source="gl"),
                    _dimension("period", "会计期间", column="period", source="gl"),
                    _dimension("account_code", "科目编码", column="account_code", source="gl"),
                    _dimension("account_name", "科目名称", column="account_name", source="coa"),
                    _dimension("account_type", "科目类别", column="account_type", source="coa"),
                    _dimension("enterprise_name", "企业名称", column="enterprise_name", source="e"),
                ],
                metrics=[
                    _metric("opening_balance", "期初余额", column="opening_balance", source="gl", agg="sum"),
                    _metric("debit_total", "本期借方发生额", column="debit_total", source="gl", agg="sum"),
                    _metric("credit_total", "本期贷方发生额", column="credit_total", source="gl", agg="sum"),
                    _metric("closing_balance", "期末余额", column="closing_balance", source="gl", agg="sum"),
                ],
                entities=deepcopy(enterprise_only_entities),
                time=_time("period", "month", ["month", "quarter", "year"]),
                business_terms=["总账余额", "科目余额", "借方发生额", "贷方发生额"],
                analysis_patterns=["科目余额排行", "总账趋势分析", "科目结构分析"],
                evidence_requirements=["总账结论需给出科目维度", "涉及余额时建议返回期初期末余额"],
            ),
            _model(
                name="fact_journal_entry_line",
                label="凭证明细事实",
                description="按企业、期间、凭证和科目沉淀凭证明细，可用于明细穿透和凭证抽查。",
                kind="atomic_fact",
                domain="accounting",
                grain="enterprise_month_voucher_line",
                source_table="acct_journal_line",
                sources=[
                    {"table": "acct_journal_line", "alias": "jl"},
                    {"table": "acct_journal_entry", "alias": "je"},
                    {"table": "enterprise_info", "alias": "e"},
                    {"table": "acct_chart_of_accounts", "alias": "coa"},
                ],
                joins=[
                    {"left": "jl.entry_id", "right": "je.id", "type": "inner"},
                    {"left": "je.taxpayer_id", "right": "e.taxpayer_id", "type": "left"},
                    {"left": "jl.account_code", "right": "coa.account_code", "type": "left"},
                ],
                dimensions=[
                    _dimension("taxpayer_id", "纳税人识别号", column="taxpayer_id", source="je"),
                    _dimension("period", "会计期间", column="period", source="je"),
                    _dimension("entry_number", "凭证号", column="entry_number", source="je"),
                    _dimension("entry_date", "凭证日期", column="entry_date", source="je", dtype="date"),
                    _dimension("account_code", "科目编码", column="account_code", source="jl"),
                    _dimension("account_name", "科目名称", column="account_name", source="coa"),
                    _dimension("sub_account", "辅助核算", column="sub_account", source="jl"),
                    _dimension("currency", "币种", column="currency", source="jl"),
                    _dimension("is_adjusted", "是否调整凭证", column="is_adjusted", source="je", dtype="boolean"),
                    _dimension("enterprise_name", "企业名称", column="enterprise_name", source="e"),
                ],
                metrics=[
                    _metric("debit_amount", "借方金额", column="debit_amount", source="jl", agg="sum"),
                    _metric("credit_amount", "贷方金额", column="credit_amount", source="jl", agg="sum"),
                    _metric("line_count", "明细行数", expr="COUNT(*)"),
                ],
                entities=deepcopy(enterprise_only_entities),
                time=_time("period", "month", ["month"]),
                business_terms=["凭证明细", "借方金额", "贷方金额", "调整凭证"],
                analysis_patterns=["凭证穿透", "会计分录抽查", "异常凭证明细"],
                evidence_requirements=["明细穿透需返回凭证号和科目", "涉及金额时展示借贷方向"],
            ),
        ]
    )

    records.extend(
        [
            _model(
                name="mart_tax_risk_alert",
                label="税务风险预警主题",
                description="围绕风险预警主题组织税务风险指标，可直接回答企业风险预警、风险等级和阈值问题。",
                kind="composite_analysis",
                domain="risk",
                grain="enterprise_month_indicator",
                source_table="tax_risk_indicators",
                sources=[{"table": "tax_risk_indicators", "alias": "ri"}, {"table": "enterprise_info", "alias": "e"}],
                joins=[{"left": "ri.taxpayer_id", "right": "e.taxpayer_id", "type": "left"}],
                dimensions=[
                    _dimension("tax_period", "税款所属期", column="tax_period", source="ri"),
                    _dimension("enterprise_name", "企业名称", column="enterprise_name", source="e"),
                    _dimension("industry_name", "行业名称", column="industry_name", source="e"),
                    _dimension("indicator_name", "风险指标", column="indicator_name", source="ri"),
                    _dimension("risk_level", "风险等级", column="risk_level", source="ri"),
                    _dimension("alert_message", "预警信息", column="alert_message", source="ri"),
                ],
                metrics=[
                    _metric("indicator_value", "指标值", column="indicator_value", source="ri", agg="avg"),
                    _metric("threshold_value", "阈值", column="threshold_value", source="ri", agg="avg"),
                    _metric("alert_count", "预警条数", expr="COUNT(*)"),
                ],
                entities=deepcopy(shared_entities),
                time=_time("tax_period", "month", ["month", "quarter", "year"]),
                business_terms=["风险预警", "风险等级", "预警阈值", "预警信息"],
                analysis_patterns=["企业风险预警", "高风险名单", "风险等级分布"],
                evidence_requirements=["必须返回风险等级、指标值、阈值和预警信息", "企业风险结论需保留企业名称"],
                fallback_policy="fallback_to_atomic_fact",
            ),
            _model(
                name="mart_revenue_reconciliation",
                label="收入对账主题",
                description="围绕税务申报收入与会计账面收入差异组织的主题模型，用于收入对账和差异归因。",
                kind="composite_analysis",
                domain="reconciliation",
                grain="enterprise_month",
                source_table="recon_revenue_comparison",
                sources=[{"table": "recon_revenue_comparison", "alias": "rr"}, {"table": "enterprise_info", "alias": "e"}],
                joins=[{"left": "rr.taxpayer_id", "right": "e.taxpayer_id", "type": "left"}],
                dimensions=[
                    _dimension("period", "期间", column="period", source="rr"),
                    _dimension("enterprise_name", "企业名称", column="enterprise_name", source="e"),
                    _dimension("industry_name", "行业名称", column="industry_name", source="e"),
                    _dimension("diff_explanation", "差异说明", column="diff_explanation", source="rr"),
                ],
                metrics=[
                    _metric("vat_declared_revenue", "增值税申报收入", column="vat_declared_revenue", source="rr", agg="sum"),
                    _metric("cit_declared_revenue", "所得税申报收入", column="cit_declared_revenue", source="rr", agg="sum"),
                    _metric("acct_book_revenue", "账面收入", column="acct_book_revenue", source="rr", agg="sum"),
                    _metric("vat_vs_acct_diff", "增值税与账面差异", column="vat_vs_acct_diff", source="rr", agg="sum"),
                    _metric("cit_vs_acct_diff", "所得税与账面差异", column="cit_vs_acct_diff", source="rr", agg="sum"),
                    _metric("vat_vs_cit_diff", "增值税与所得税差异", column="vat_vs_cit_diff", source="rr", agg="sum"),
                    _metric("max_abs_diff", "最大绝对差异", expr='MAX(ABS("rr"."vat_vs_acct_diff"))'),
                ],
                entities=deepcopy(shared_entities),
                time=_time("period", "month", ["month", "quarter", "year"]),
                business_terms=["收入对账", "税会差异", "账面收入", "差异说明"],
                intent_aliases=["收入差异", "税会收入对比", "申报收入对账"],
                analysis_patterns=["企业收入对账", "差异归因", "税会口径比较"],
                evidence_requirements=["必须返回三个口径收入中的至少两个", "差异归因需给出差异说明"],
                fallback_policy="fallback_to_atomic_fact",
            ),
            _model(
                name="mart_tax_burden_analysis",
                label="税负分析主题",
                description="围绕企业税负与行业基准偏离组织的主题模型，用于税负偏离和行业比较。",
                kind="composite_analysis",
                domain="reconciliation",
                grain="enterprise_month",
                source_table="recon_tax_burden_analysis",
                sources=[
                    {"table": "recon_tax_burden_analysis", "alias": "tb"},
                    {"table": "enterprise_info", "alias": "e"},
                    {"table": "dict_industry", "alias": "di"},
                ],
                joins=[
                    {"left": "tb.taxpayer_id", "right": "e.taxpayer_id", "type": "left"},
                    {"left": "tb.industry_code", "right": "di.industry_code", "type": "left"},
                ],
                dimensions=[
                    _dimension("period", "期间", column="period", source="tb"),
                    _dimension("enterprise_name", "企业名称", column="enterprise_name", source="e"),
                    _dimension("industry_code", "行业代码", column="industry_code", source="tb"),
                    _dimension("industry_name", "行业名称", column="industry_name", source="di"),
                ],
                metrics=[
                    _metric("vat_burden_rate", "增值税税负率", column="vat_burden_rate", source="tb", agg="avg", fmt="percent"),
                    _metric("cit_effective_rate", "所得税有效税率", column="cit_effective_rate", source="tb", agg="avg", fmt="percent"),
                    _metric("total_tax_burden", "综合税负率", column="total_tax_burden", source="tb", agg="avg", fmt="percent"),
                    _metric("industry_avg_vat_burden", "行业平均增值税税负率", column="industry_avg_vat_burden", source="tb", agg="avg", fmt="percent"),
                    _metric("industry_avg_cit_rate", "行业平均所得税税率", column="industry_avg_cit_rate", source="tb", agg="avg", fmt="percent"),
                    _metric("deviation_vat", "增值税税负偏离度", column="deviation_vat", source="tb", agg="avg", fmt="percent"),
                    _metric("deviation_cit", "所得税税负偏离度", column="deviation_cit", source="tb", agg="avg", fmt="percent"),
                ],
                entities=deepcopy(shared_entities),
                time=_time("period", "month", ["month", "quarter", "year"]),
                business_terms=["税负率", "行业基准", "偏离度", "综合税负"],
                analysis_patterns=["税负偏离分析", "行业税负对比", "税负风险识别"],
                evidence_requirements=["税负分析必须给出企业值和行业基准", "偏离结论需返回行业维度"],
                fallback_policy="fallback_to_atomic_fact",
            ),
            _model(
                name="mart_adjustment_tracking",
                label="纳税调整追踪主题",
                description="围绕纳税调整与递延税影响组织的主题模型，用于差异来源追踪。",
                kind="composite_analysis",
                domain="reconciliation",
                grain="enterprise_month_adjustment",
                source_table="recon_adjustment_tracking",
                sources=[{"table": "recon_adjustment_tracking", "alias": "at"}, {"table": "enterprise_info", "alias": "e"}],
                joins=[{"left": "at.taxpayer_id", "right": "e.taxpayer_id", "type": "left"}],
                dimensions=[
                    _dimension("period", "期间", column="period", source="at"),
                    _dimension("enterprise_name", "企业名称", column="enterprise_name", source="e"),
                    _dimension("adjustment_type", "差异类型", column="adjustment_type", source="at"),
                    _dimension("source_category", "差异来源", column="source_category", source="at"),
                ],
                metrics=[
                    _metric("accounting_amount", "会计金额", column="accounting_amount", source="at", agg="sum"),
                    _metric("tax_amount", "税法金额", column="tax_amount", source="at", agg="sum"),
                    _metric("difference", "差异金额", column="difference", source="at", agg="sum"),
                    _metric("deferred_tax_impact", "递延所得税影响", column="deferred_tax_impact", source="at", agg="sum"),
                ],
                entities=deepcopy(enterprise_only_entities),
                time=_time("period", "month", ["month", "quarter", "year"]),
                business_terms=["纳税调整追踪", "差异来源", "递延所得税影响"],
                analysis_patterns=["差异来源追踪", "暂时性差异分析"],
                evidence_requirements=["调整追踪必须返回差异来源", "递延税分析需展示差异金额和递延影响"],
                fallback_policy="fallback_to_atomic_fact",
            ),
            _model(
                name="mart_cross_check_result",
                label="交叉核验主题",
                description="围绕核验规则、预期值和实际值组织的主题模型，用于一致性校验和异常发现。",
                kind="composite_analysis",
                domain="reconciliation",
                grain="enterprise_month_check_rule",
                source_table="recon_cross_check_result",
                sources=[{"table": "recon_cross_check_result", "alias": "cc"}, {"table": "enterprise_info", "alias": "e"}],
                joins=[{"left": "cc.taxpayer_id", "right": "e.taxpayer_id", "type": "left"}],
                dimensions=[
                    _dimension("period", "期间", column="period", source="cc"),
                    _dimension("enterprise_name", "企业名称", column="enterprise_name", source="e"),
                    _dimension("check_rule_code", "核验规则编码", column="check_rule_code", source="cc"),
                    _dimension("check_rule_name", "核验规则名称", column="check_rule_name", source="cc"),
                    _dimension("status", "核验结果", column="status", source="cc"),
                    _dimension("recommendation", "建议", column="recommendation", source="cc"),
                ],
                metrics=[
                    _metric("expected_value", "预期值", column="expected_value", source="cc", agg="sum"),
                    _metric("actual_value", "实际值", column="actual_value", source="cc", agg="sum"),
                    _metric("difference", "差异", column="difference", source="cc", agg="sum"),
                    _metric("check_count", "核验条数", expr="COUNT(*)"),
                ],
                entities=deepcopy(enterprise_only_entities),
                time=_time("period", "month", ["month", "quarter", "year"]),
                business_terms=["交叉核验", "预期值", "实际值", "异常规则"],
                analysis_patterns=["一致性校验", "异常规则发现", "核验结果跟踪"],
                evidence_requirements=["核验结论需返回规则名称和结果状态", "异常结论需附建议"],
                fallback_policy="fallback_to_atomic_fact",
            ),
        ]
    )

    records.extend(
        [
            _model(
                name="fact_cit_adjustment_item",
                label="纳税调整明细事实",
                description="按企业、年度和调整项目沉淀税会调整明细，用于差异来源追踪。",
                kind="atomic_fact",
                domain="tax",
                grain="enterprise_year_adjustment_item",
                source_table="tax_cit_adjustment_items",
                sources=[{"table": "tax_cit_adjustment_items", "alias": "aj"}, {"table": "enterprise_info", "alias": "e"}],
                joins=[{"left": "aj.taxpayer_id", "right": "e.taxpayer_id", "type": "left"}],
                dimensions=[
                    _dimension("taxpayer_id", "纳税人识别号", column="taxpayer_id", source="aj"),
                    _dimension("tax_year", "纳税年度", column="tax_year", source="aj", dtype="number"),
                    _dimension("item_code", "调整项目编码", column="item_code", source="aj"),
                    _dimension("item_name", "调整项目名称", column="item_name", source="aj"),
                    _dimension("adjustment_direction", "调整方向", column="adjustment_direction", source="aj"),
                    _dimension("enterprise_name", "企业名称", column="enterprise_name", source="e"),
                ],
                metrics=[
                    _metric("accounting_amount", "会计金额", column="accounting_amount", source="aj", agg="sum"),
                    _metric("tax_amount", "税法金额", column="tax_amount", source="aj", agg="sum"),
                    _metric("adjustment_amount", "调整金额", column="adjustment_amount", source="aj", agg="sum"),
                ],
                entities=deepcopy(enterprise_only_entities),
                time=_time("tax_year", "year", ["year"]),
                business_terms=["纳税调整", "调增", "调减", "税会差异项目"],
                analysis_patterns=["调整项目排行", "税会差异溯源"],
                evidence_requirements=["必须返回项目名称和方向", "差异分析需展示会计金额与税法金额"],
            ),
            _model(
                name="fact_other_tax_declaration",
                label="其他税种申报事实",
                description="按企业、月份和税种沉淀其他税种申报事实，可用于城建税、印花税等税种分析。",
                kind="atomic_fact",
                domain="tax",
                grain="enterprise_month_tax_type",
                source_table="tax_other_taxes",
                sources=[{"table": "tax_other_taxes", "alias": "ot"}, {"table": "enterprise_info", "alias": "e"}],
                joins=[{"left": "ot.taxpayer_id", "right": "e.taxpayer_id", "type": "left"}],
                dimensions=[
                    _dimension("taxpayer_id", "纳税人识别号", column="taxpayer_id", source="ot"),
                    _dimension("tax_period", "税款所属期", column="tax_period", source="ot"),
                    _dimension("tax_type", "税种", column="tax_type", source="ot"),
                    _dimension("enterprise_name", "企业名称", column="enterprise_name", source="e"),
                ],
                metrics=[
                    _metric("tax_basis", "计税依据", column="tax_basis", source="ot", agg="sum"),
                    _metric("tax_rate", "税率", column="tax_rate", source="ot", agg="avg", fmt="percent"),
                    _metric("tax_amount", "应纳税额", column="tax_amount", source="ot", agg="sum"),
                ],
                entities=deepcopy(enterprise_only_entities),
                time=_time("tax_period", "month", ["month", "quarter", "year"]),
                business_terms=["其他税种", "印花税", "城建税", "税额"],
                analysis_patterns=["税种分布分析", "税种趋势分析"],
                evidence_requirements=["必须返回税种", "涉及税额结论时给出计税依据"],
            ),
            _model(
                name="fact_tax_risk_indicator",
                label="税务风险指标事实",
                description="按企业和月份沉淀税务风险指标、阈值和预警信息，是风险类问题的基础事实模型。",
                kind="atomic_fact",
                domain="risk",
                grain="enterprise_month_indicator",
                source_table="tax_risk_indicators",
                sources=[{"table": "tax_risk_indicators", "alias": "ri"}, {"table": "enterprise_info", "alias": "e"}],
                joins=[{"left": "ri.taxpayer_id", "right": "e.taxpayer_id", "type": "left"}],
                dimensions=[
                    _dimension("taxpayer_id", "纳税人识别号", column="taxpayer_id", source="ri"),
                    _dimension("tax_period", "税款所属期", column="tax_period", source="ri"),
                    _dimension("indicator_code", "指标编码", column="indicator_code", source="ri"),
                    _dimension("indicator_name", "指标名称", column="indicator_name", source="ri"),
                    _dimension("risk_level", "风险等级", column="risk_level", source="ri"),
                    _dimension("alert_message", "预警信息", column="alert_message", source="ri"),
                    _dimension("enterprise_name", "企业名称", column="enterprise_name", source="e"),
                    _dimension("industry_name", "行业名称", column="industry_name", source="e"),
                ],
                metrics=[
                    _metric("indicator_value", "指标值", column="indicator_value", source="ri", agg="avg"),
                    _metric("threshold_value", "阈值", column="threshold_value", source="ri", agg="avg"),
                    _metric("alert_count", "预警条数", expr="COUNT(*)"),
                ],
                entities=deepcopy(shared_entities),
                time=_time("tax_period", "month", ["month", "quarter", "year"]),
                business_terms=["风险指标", "风险等级", "预警阈值", "预警信息"],
                intent_aliases=["风险预警", "风险提示", "税务风险"],
                analysis_patterns=["风险预警列表", "高风险企业识别", "风险等级分布"],
                evidence_requirements=["必须返回风险等级、指标值和阈值", "风险结论需要附预警信息"],
            ),
            _model(
                name="fact_income_statement",
                label="利润表事实",
                description="按企业和月份沉淀利润表科目，用于收入、成本、费用和净利润分析。",
                kind="atomic_fact",
                domain="accounting",
                grain="enterprise_month",
                source_table="acct_income_statement",
                sources=[{"table": "acct_income_statement", "alias": "isf"}, {"table": "enterprise_info", "alias": "e"}],
                joins=[{"left": "isf.taxpayer_id", "right": "e.taxpayer_id", "type": "left"}],
                dimensions=[
                    _dimension("taxpayer_id", "纳税人识别号", column="taxpayer_id", source="isf"),
                    _dimension("period", "会计期间", column="period", source="isf"),
                    _dimension("enterprise_name", "企业名称", column="enterprise_name", source="e"),
                    _dimension("industry_name", "行业名称", column="industry_name", source="e"),
                ],
                metrics=[
                    _metric("revenue_main", "主营业务收入", column="revenue_main", source="isf", agg="sum"),
                    _metric("revenue_other", "其他业务收入", column="revenue_other", source="isf", agg="sum"),
                    _metric("cost_main", "主营业务成本", column="cost_main", source="isf", agg="sum"),
                    _metric("cost_other", "其他业务成本", column="cost_other", source="isf", agg="sum"),
                    _metric("tax_surcharges", "税金及附加", column="tax_surcharges", source="isf", agg="sum"),
                    _metric("admin_expenses", "管理费用", column="admin_expenses", source="isf", agg="sum"),
                    _metric("finance_expenses", "财务费用", column="finance_expenses", source="isf", agg="sum"),
                    _metric("profit_total", "利润总额", column="profit_total", source="isf", agg="sum"),
                    _metric("income_tax_expense", "所得税费用", column="income_tax_expense", source="isf", agg="sum"),
                    _metric("net_profit", "净利润", column="net_profit", source="isf", agg="sum"),
                    _metric("book_revenue_total", "账面收入合计", expr='SUM("isf"."revenue_main" + "isf"."revenue_other")'),
                ],
                entities=deepcopy(shared_entities),
                time=_time("period", "month", ["month", "quarter", "year"]),
                business_terms=["利润表", "账面收入", "利润总额", "净利润"],
                analysis_patterns=["利润趋势分析", "收入成本对比", "利润率分析"],
                evidence_requirements=["利润结论需要同时展示收入和利润", "账面收入使用主营和其他业务收入合计"],
            ),
        ]
    )

    records.extend(
        [
            _model(
                name="mart_revenue_timing_gap",
                label="收入错期诊断主题",
                description="围绕申报收入与账面收入差异、错期说明和差异率组织的主题模型，用于定位时间性差异。", 
                kind="composite_analysis",
                domain="reconciliation",
                grain="enterprise_month",
                source_table="recon_revenue_comparison",
                sources=[{"table": "recon_revenue_comparison", "alias": "rc"}, {"table": "enterprise_info", "alias": "e"}],
                joins=[{"left": "rc.taxpayer_id", "right": "e.taxpayer_id", "type": "left"}],
                dimensions=[
                    _dimension("period", "期间", column="period", source="rc"),
                    _dimension("enterprise_name", "企业名称", column="enterprise_name", source="e"),
                    _dimension("industry_name", "行业名称", column="industry_name", source="e"),
                    _dimension("diff_explanation", "差异说明", column="diff_explanation", source="rc"),
                ],
                metrics=[
                    _metric("vat_declared_revenue", "申报收入", column="vat_declared_revenue", source="rc", agg="sum"),
                    _metric("acct_book_revenue", "账面收入", column="acct_book_revenue", source="rc", agg="sum"),
                    _metric("revenue_gap_amount", "收入差异金额", column="vat_vs_acct_diff", source="rc", agg="sum"),
                    _metric(
                        "revenue_gap_rate",
                        "收入差异率",
                        expr='CASE WHEN SUM("rc"."acct_book_revenue") = 0 THEN 0 ELSE SUM("rc"."vat_vs_acct_diff") / NULLIF(SUM("rc"."acct_book_revenue"), 0) END',
                        fmt="percent",
                        depends_on=["revenue_gap_amount", "acct_book_revenue"],
                    ),
                    _metric(
                        "timing_case_count",
                        "时间性差异笔数",
                        expr='SUM(CASE WHEN "rc"."diff_explanation" LIKE \'%时间性差异%\' THEN 1 ELSE 0 END)',
                    ),
                ],
                entities=deepcopy(shared_entities),
                time=_time("period", "month", ["month", "quarter", "year"]),
                business_terms=["时间性差异", "收入错期", "开票与确认时点差异", "收入对账"],
                intent_aliases=["错期差异", "收入错期", "时间性差异"],
                analysis_patterns=["时间性差异诊断", "收入差异率分析", "错期案例定位"],
                evidence_requirements=["必须返回差异金额和差异说明", "差异诊断需展示账面收入和申报收入"],
                detail_fields=[
                    _dimension("period", "期间", column="period", source="rc"),
                    _dimension("enterprise_name", "企业名称", column="enterprise_name", source="e"),
                    _dimension("diff_explanation", "差异说明", column="diff_explanation", source="rc"),
                    _dimension("vat_declared_revenue_detail", "申报收入", expr='"rc"."vat_declared_revenue"', dtype="number"),
                    _dimension("acct_book_revenue_detail", "账面收入", expr='"rc"."acct_book_revenue"', dtype="number"),
                    _dimension("revenue_gap_amount_detail", "收入差异金额", expr='"rc"."vat_vs_acct_diff"', dtype="number"),
                ],
            ),
            _model(
                name="mart_vat_payable_snapshot",
                label="应交税费滚动主题",
                description="围绕应交税费期初、计提、缴纳和期末余额组织的主题模型，用于税额滚动和账税余额核对。",
                kind="composite_analysis",
                domain="tax",
                grain="enterprise_month_tax_type",
                source_table="acct_tax_payable_detail",
                sources=[{"table": "acct_tax_payable_detail", "alias": "tp"}, {"table": "enterprise_info", "alias": "e"}],
                joins=[{"left": "tp.taxpayer_id", "right": "e.taxpayer_id", "type": "left"}],
                dimensions=[
                    _dimension("period", "期间", column="period", source="tp"),
                    _dimension("enterprise_name", "企业名称", column="enterprise_name", source="e"),
                    _dimension("industry_name", "行业名称", column="industry_name", source="e"),
                    _dimension("tax_type", "税种", column="tax_type", source="tp"),
                ],
                metrics=[
                    _metric("opening_balance", "期初余额", column="opening_balance", source="tp", agg="sum"),
                    _metric("accrued_amount", "本期计提", column="accrued_amount", source="tp", agg="sum"),
                    _metric("paid_amount", "本期缴纳", column="paid_amount", source="tp", agg="sum"),
                    _metric("closing_balance", "期末余额", column="closing_balance", source="tp", agg="sum"),
                    _metric(
                        "net_change",
                        "净变动额",
                        expr='SUM("tp"."accrued_amount" - "tp"."paid_amount")',
                        depends_on=["accrued_amount", "paid_amount"],
                    ),
                ],
                entities=deepcopy(shared_entities),
                time=_time("period", "month", ["month", "quarter", "year"]),
                business_terms=["应交税费", "税费余额", "税额滚动", "本期计提"],
                analysis_patterns=["税费滚动分析", "账面税费余额核对", "按税种余额查看"],
                evidence_requirements=["必须返回税种和期末余额", "滚动分析需展示计提与缴纳"],
            ),
            _model(
                name="mart_cit_adjustment_bridge",
                label="所得税调整桥接主题",
                description="围绕纳税调整项目、税会金额差、调增调减方向组织的主题模型，用于所得税桥接分析。",
                kind="composite_analysis",
                domain="reconciliation",
                grain="enterprise_year_adjustment_item",
                source_table="tax_cit_adjustment_items",
                sources=[{"table": "tax_cit_adjustment_items", "alias": "aj"}, {"table": "enterprise_info", "alias": "e"}],
                joins=[{"left": "aj.taxpayer_id", "right": "e.taxpayer_id", "type": "left"}],
                dimensions=[
                    _dimension("tax_year", "纳税年度", column="tax_year", source="aj", dtype="number"),
                    _dimension("enterprise_name", "企业名称", column="enterprise_name", source="e"),
                    _dimension("item_name", "调整项目名称", column="item_name", source="aj"),
                    _dimension("adjustment_direction", "调整方向", column="adjustment_direction", source="aj"),
                ],
                metrics=[
                    _metric("accounting_amount", "会计金额", column="accounting_amount", source="aj", agg="sum"),
                    _metric("tax_amount", "税法金额", column="tax_amount", source="aj", agg="sum"),
                    _metric("adjustment_amount", "调整金额", column="adjustment_amount", source="aj", agg="sum"),
                    _metric(
                        "tax_book_gap",
                        "税会金额差",
                        expr='SUM("aj"."tax_amount") - SUM("aj"."accounting_amount")',
                        depends_on=["tax_amount", "accounting_amount"],
                    ),
                    _metric(
                        "positive_adjustment_amount",
                        "调增金额",
                        expr='SUM(CASE WHEN "aj"."adjustment_direction" = \'调增\' THEN "aj"."adjustment_amount" ELSE 0 END)',
                    ),
                    _metric(
                        "negative_adjustment_amount",
                        "调减金额",
                        expr='SUM(CASE WHEN "aj"."adjustment_direction" = \'调减\' THEN "aj"."adjustment_amount" ELSE 0 END)',
                    ),
                ],
                entities=deepcopy(enterprise_only_entities),
                time=_time("tax_year", "year", ["year"]),
                business_terms=["纳税调整桥", "调增", "调减", "税会桥接", "所得税桥"],
                analysis_patterns=["所得税桥接分析", "调整项目排行", "调增调减结构查看"],
                evidence_requirements=["必须返回调整项目和方向", "桥接结论需展示税法金额与会计金额"],
            ),
            _model(
                name="mart_cit_settlement_bridge",
                label="所得税汇缴桥接主题",
                description="围绕会计利润、纳税调整、应纳税所得额、预缴税额和汇缴结果组织的主题模型，用于所得税汇算清缴桥接分析。",
                kind="composite_analysis",
                domain="reconciliation",
                grain="enterprise_year",
                source_table="tax_cit_annual",
                sources=[{"table": "tax_cit_annual", "alias": "ca"}, {"table": "enterprise_info", "alias": "e"}],
                joins=[{"left": "ca.taxpayer_id", "right": "e.taxpayer_id", "type": "left"}],
                dimensions=[
                    _dimension("tax_year", "纳税年度", column="tax_year", source="ca", dtype="number"),
                    _dimension("enterprise_name", "企业名称", column="enterprise_name", source="e"),
                    _dimension("industry_name", "行业名称", column="industry_name", source="e"),
                    _dimension("registration_type", "纳税人类型", column="registration_type", source="e"),
                ],
                metrics=[
                    _metric("accounting_profit", "会计利润", column="accounting_profit", source="ca", agg="sum"),
                    _metric("tax_adjustments_increase", "纳税调增", column="tax_adjustments_increase", source="ca", agg="sum"),
                    _metric("tax_adjustments_decrease", "纳税调减", column="tax_adjustments_decrease", source="ca", agg="sum"),
                    _metric("taxable_income", "应纳税所得额", column="taxable_income", source="ca", agg="sum"),
                    _metric("tax_amount", "应纳所得税额", column="tax_amount", source="ca", agg="sum"),
                    _metric("tax_prepaid", "已预缴税额", column="tax_prepaid", source="ca", agg="sum"),
                    _metric("tax_refund_or_due", "应补退税额", column="tax_refund_or_due", source="ca", agg="sum"),
                    _metric(
                        "net_tax_adjustment",
                        "纳税调整净额",
                        expr='SUM("ca"."tax_adjustments_increase") - SUM("ca"."tax_adjustments_decrease")',
                        depends_on=["tax_adjustments_increase", "tax_adjustments_decrease"],
                    ),
                    _metric(
                        "effective_tax_rate",
                        "有效所得税率",
                        expr='CASE WHEN SUM("ca"."accounting_profit") = 0 THEN 0 ELSE SUM("ca"."tax_amount") / NULLIF(SUM("ca"."accounting_profit"), 0) END',
                        fmt="percent",
                        depends_on=["tax_amount", "accounting_profit"],
                    ),
                    _metric(
                        "settlement_gap",
                        "汇缴差异额",
                        expr='SUM("ca"."tax_amount") - SUM("ca"."tax_prepaid")',
                        depends_on=["tax_amount", "tax_prepaid"],
                    ),
                ],
                entities=deepcopy(enterprise_only_entities),
                time=_time("tax_year", "year", ["year"]),
                business_terms=["汇算清缴", "纳税调整", "应纳税所得额", "已预缴税额", "应补退税额"],
                intent_aliases=["汇算清缴桥接", "所得税桥接", "汇缴桥接", "应补退税额分析"],
                analysis_patterns=["所得税汇缴桥接分析", "会计利润到所得额桥接", "汇缴差额定位"],
                evidence_requirements=["必须返回会计利润、纳税调增调减和应纳税所得额", "汇缴结论需展示应纳税额、预缴税额和应补退税额"],
                detail_fields=[
                    _dimension("tax_year", "纳税年度", column="tax_year", source="ca", dtype="number"),
                    _dimension("enterprise_name", "企业名称", column="enterprise_name", source="e"),
                    _dimension("registration_type", "纳税人类型", column="registration_type", source="e"),
                    _dimension("accounting_profit_detail", "会计利润", expr='"ca"."accounting_profit"', dtype="number"),
                    _dimension("taxable_income_detail", "应纳税所得额", expr='"ca"."taxable_income"', dtype="number"),
                    _dimension("tax_amount_detail", "应纳所得税额", expr='"ca"."tax_amount"', dtype="number"),
                    _dimension("tax_prepaid_detail", "已预缴税额", expr='"ca"."tax_prepaid"', dtype="number"),
                    _dimension("tax_refund_or_due_detail", "应补退税额", expr='"ca"."tax_refund_or_due"', dtype="number"),
                ],
            ),
            _model(
                name="mart_vat_declaration_diagnostics",
                label="增值税申报诊断主题",
                description="围绕销项税额、进项税额、转出项、应纳税额和销售额结构组织的主题模型，用于增值税申报波动和税负诊断。",
                kind="composite_analysis",
                domain="tax",
                grain="enterprise_month",
                source_table="tax_vat_declaration",
                sources=[{"table": "tax_vat_declaration", "alias": "vd"}, {"table": "enterprise_info", "alias": "e"}],
                joins=[{"left": "vd.taxpayer_id", "right": "e.taxpayer_id", "type": "left"}],
                dimensions=[
                    _dimension("tax_period", "税款所属期", column="tax_period", source="vd"),
                    _dimension("enterprise_name", "企业名称", column="enterprise_name", source="e"),
                    _dimension("industry_name", "行业名称", column="industry_name", source="e"),
                    _dimension("registration_type", "纳税人类型", column="registration_type", source="e"),
                ],
                metrics=[
                    _metric("total_sales_amount", "销售额合计", column="total_sales_amount", source="vd", agg="sum"),
                    _metric("taxable_sales_amount", "应税销售额", column="taxable_sales_amount", source="vd", agg="sum"),
                    _metric("exempt_sales_amount", "免税销售额", column="exempt_sales_amount", source="vd", agg="sum"),
                    _metric("output_tax_amount", "销项税额", column="output_tax_amount", source="vd", agg="sum"),
                    _metric("input_tax_amount", "进项税额", column="input_tax_amount", source="vd", agg="sum"),
                    _metric("input_tax_transferred_out", "进项税额转出", column="input_tax_transferred_out", source="vd", agg="sum"),
                    _metric("tax_payable", "应纳税额", column="tax_payable", source="vd", agg="sum"),
                    _metric(
                        "input_output_gap",
                        "进销项税额差",
                        expr='SUM("vd"."output_tax_amount") - SUM("vd"."input_tax_amount") + SUM("vd"."input_tax_transferred_out")',
                        depends_on=["output_tax_amount", "input_tax_amount", "input_tax_transferred_out"],
                    ),
                    _metric(
                        "declaration_effective_rate",
                        "申报有效税负率",
                        expr='CASE WHEN SUM("vd"."taxable_sales_amount") = 0 THEN 0 ELSE SUM("vd"."tax_payable") / NULLIF(SUM("vd"."taxable_sales_amount"), 0) END',
                        fmt="percent",
                        depends_on=["tax_payable", "taxable_sales_amount"],
                    ),
                    _metric(
                        "exempt_sales_ratio",
                        "免税销售额占比",
                        expr='CASE WHEN SUM("vd"."total_sales_amount") = 0 THEN 0 ELSE SUM("vd"."exempt_sales_amount") / NULLIF(SUM("vd"."total_sales_amount"), 0) END',
                        fmt="percent",
                        depends_on=["exempt_sales_amount", "total_sales_amount"],
                    ),
                ],
                entities=deepcopy(shared_entities),
                time=_time("tax_period", "month", ["month", "quarter", "year"]),
                business_terms=["销项税额", "进项税额", "转出", "应纳税额", "免税销售额"],
                intent_aliases=["增值税申报诊断", "进销项分析", "进销项转出影响", "税负诊断"],
                analysis_patterns=["申报税额诊断", "进销项结构分析", "免税销售占比查看"],
                evidence_requirements=["必须返回销项、进项、转出和应纳税额", "申报税负结论需展示销售额口径"],
                detail_fields=[
                    _dimension("tax_period", "税款所属期", column="tax_period", source="vd"),
                    _dimension("enterprise_name", "企业名称", column="enterprise_name", source="e"),
                    _dimension("registration_type", "纳税人类型", column="registration_type", source="e"),
                    _dimension("taxable_sales_amount_detail", "应税销售额", expr='"vd"."taxable_sales_amount"', dtype="number"),
                    _dimension("output_tax_amount_detail", "销项税额", expr='"vd"."output_tax_amount"', dtype="number"),
                    _dimension("input_tax_amount_detail", "进项税额", expr='"vd"."input_tax_amount"', dtype="number"),
                    _dimension("input_tax_transferred_out_detail", "进项税额转出", expr='"vd"."input_tax_transferred_out"', dtype="number"),
                    _dimension("tax_payable_detail", "应纳税额", expr='"vd"."tax_payable"', dtype="number"),
                ],
            ),
            _model(
                name="mart_depreciation_timing_difference",
                label="折旧税会差异主题",
                description="围绕固定资产会计折旧、税法折旧和月差异组织的主题模型，用于暂时性差异和折旧口径不一致诊断。",
                kind="composite_analysis",
                domain="reconciliation",
                grain="enterprise_asset",
                source_table="acct_depreciation_schedule",
                sources=[{"table": "acct_depreciation_schedule", "alias": "ds"}, {"table": "enterprise_info", "alias": "e"}],
                joins=[{"left": "ds.taxpayer_id", "right": "e.taxpayer_id", "type": "left"}],
                dimensions=[
                    _dimension("enterprise_name", "企业名称", column="enterprise_name", source="e"),
                    _dimension("industry_name", "行业名称", column="industry_name", source="e"),
                    _dimension("asset_id", "资产编号", column="asset_id", source="ds"),
                    _dimension("asset_name", "资产名称", column="asset_name", source="ds"),
                    _dimension("category", "资产类别", column="category", source="ds"),
                    _dimension("acct_method", "会计折旧方法", column="acct_method", source="ds"),
                    _dimension("tax_method", "税法折旧方法", column="tax_method", source="ds"),
                ],
                metrics=[
                    _metric("original_value", "原值", column="original_value", source="ds", agg="sum"),
                    _metric("acct_depreciation_monthly", "会计月折旧", column="acct_depreciation_monthly", source="ds", agg="sum"),
                    _metric("tax_depreciation_monthly", "税法月折旧", column="tax_depreciation_monthly", source="ds", agg="sum"),
                    _metric("difference_monthly", "月差异", column="difference_monthly", source="ds", agg="sum"),
                    _metric("asset_count", "资产数量", expr="COUNT(*)"),
                    _metric(
                        "depreciation_gap_rate",
                        "折旧差异率",
                        expr='CASE WHEN SUM("ds"."acct_depreciation_monthly") = 0 THEN 0 ELSE SUM("ds"."difference_monthly") / NULLIF(SUM("ds"."acct_depreciation_monthly"), 0) END',
                        fmt="percent",
                        depends_on=["difference_monthly", "acct_depreciation_monthly"],
                    ),
                ],
                entities=deepcopy(shared_entities),
                business_terms=["折旧差异", "暂时性差异", "会计折旧", "税法折旧", "资产类别"],
                analysis_patterns=["折旧差异诊断", "资产级差异下钻", "暂时性差异识别"],
                evidence_requirements=["必须返回资产名称或资产类别", "差异结论需同时展示会计折旧和税法折旧"],
                detail_fields=[
                    _dimension("enterprise_name", "企业名称", column="enterprise_name", source="e"),
                    _dimension("asset_id", "资产编号", column="asset_id", source="ds"),
                    _dimension("asset_name", "资产名称", column="asset_name", source="ds"),
                    _dimension("category", "资产类别", column="category", source="ds"),
                    _dimension("acct_method", "会计折旧方法", column="acct_method", source="ds"),
                    _dimension("tax_method", "税法折旧方法", column="tax_method", source="ds"),
                    _dimension("acct_depreciation_monthly_detail", "会计月折旧", expr='"ds"."acct_depreciation_monthly"', dtype="number"),
                    _dimension("tax_depreciation_monthly_detail", "税法月折旧", expr='"ds"."tax_depreciation_monthly"', dtype="number"),
                    _dimension("difference_monthly_detail", "月差异", expr='"ds"."difference_monthly"', dtype="number"),
                ],
            ),
        ]
    )

    records.extend(
        [
            _model(
                name="fact_export_book_revenue_line",
                label="出口账面收入明细事实",
                description="按合同明细行沉淀出口账面收入、非税基扣减项和单证信息，用于出口退税账面口径追溯。",
                kind="atomic_fact",
                domain="reconciliation",
                grain="enterprise_contract_line",
                source_table="recon_export_book_revenue_line",
                sources=[{"table": "recon_export_book_revenue_line", "alias": "br"}, {"table": "enterprise_info", "alias": "e"}],
                joins=[{"left": "br.taxpayer_id", "right": "e.taxpayer_id", "type": "left"}],
                dimensions=[
                    _dimension("taxpayer_id", "纳税人识别号", column="taxpayer_id", source="br"),
                    _dimension("book_period", "账面期间", column="book_period", source="br"),
                    _dimension("recognition_date", "收入确认日期", column="recognition_date", source="br"),
                    _dimension("contract_id", "合同号", column="contract_id", source="br"),
                    _dimension("contract_line_id", "合同明细行号", column="contract_line_id", source="br"),
                    _dimension("customer_name", "客户名称", column="customer_name", source="br"),
                    _dimension("product_name", "产品名称", column="product_name", source="br"),
                    _dimension("shipment_no", "发运单号", column="shipment_no", source="br"),
                    _dimension("declaration_no", "报关单号", column="declaration_no", source="br"),
                    _dimension("declaration_line_no", "报关单行号", column="declaration_line_no", source="br", dtype="number"),
                    _dimension("sales_invoice_no", "销售发票号", column="sales_invoice_no", source="br"),
                    _dimension("voucher_no", "凭证号", column="voucher_no", source="br"),
                    _dimension("currency_code", "币种", column="currency_code", source="br"),
                    _dimension("source_system", "来源系统", column="source_system", source="br"),
                    _dimension("doc_status", "单据状态", column="doc_status", source="br"),
                    _dimension("enterprise_name", "企业名称", column="enterprise_name", source="e"),
                    _dimension("industry_name", "行业名称", column="industry_name", source="e"),
                ],
                metrics=[
                    _metric("gross_revenue_amount_cny", "毛收入人民币", column="gross_revenue_amount_cny", source="br", agg="sum"),
                    _metric("freight_amount_cny", "运费人民币", column="freight_amount_cny", source="br", agg="sum"),
                    _metric("insurance_amount_cny", "保费人民币", column="insurance_amount_cny", source="br", agg="sum"),
                    _metric("commission_amount_cny", "佣金人民币", column="commission_amount_cny", source="br", agg="sum"),
                    _metric("book_non_basis_exclusion_amount_cny", "账面非税基扣减额", column="book_non_basis_exclusion_amount_cny", source="br", agg="sum"),
                    _metric("book_net_revenue_before_discount_cny", "折扣前账面可比收入", column="book_net_revenue_before_discount_cny", source="br", agg="sum"),
                    _metric("book_line_count", "账面收入行数", expr='COUNT(*)'),
                ],
                entities=deepcopy(shared_entities),
                time=_time_with_roles(
                    "book_period",
                    "month",
                    ["month", "quarter", "year"],
                    default_role="book_period",
                    roles={
                        "book_period": {"field": "book_period", "grain": "month"},
                        "recognition_date": {"field": "recognition_date", "grain": "day", "range_mode": "date"},
                    },
                ),
                business_terms=["出口收入", "账面收入", "合同号", "报关单", "非税基扣减"],
                intent_aliases=["出口账面收入明细", "出口收入单证链", "出口账面口径"],
                analysis_patterns=["出口收入追溯", "合同明细定位", "detail"],
                evidence_requirements=["必须返回合同号、报关单号或凭证号中的至少一个", "账面口径需展示非税基扣减项与可比收入"],
            ),
            _model(
                name="fact_export_refund_tax_basis_line",
                label="出口退税税基明细事实",
                description="按合同明细行沉淀出口退税税基、退税率、不可退税金额和报关单信息，用于税基口径追溯。",
                kind="atomic_fact",
                domain="reconciliation",
                grain="enterprise_contract_line",
                source_table="recon_export_refund_tax_basis_line",
                sources=[{"table": "recon_export_refund_tax_basis_line", "alias": "tb"}, {"table": "enterprise_info", "alias": "e"}],
                joins=[{"left": "tb.taxpayer_id", "right": "e.taxpayer_id", "type": "left"}],
                dimensions=[
                    _dimension("taxpayer_id", "纳税人识别号", column="taxpayer_id", source="tb"),
                    _dimension("rebate_period", "退税所属期", column="rebate_period", source="tb"),
                    _dimension("export_date", "出口日期", column="export_date", source="tb"),
                    _dimension("contract_id", "合同号", column="contract_id", source="tb"),
                    _dimension("contract_line_id", "合同明细行号", column="contract_line_id", source="tb"),
                    _dimension("customer_name", "客户名称", column="customer_name", source="tb"),
                    _dimension("product_name", "产品名称", column="product_name", source="tb"),
                    _dimension("declaration_no", "报关单号", column="declaration_no", source="tb"),
                    _dimension("declaration_line_no", "报关单行号", column="declaration_line_no", source="tb", dtype="number"),
                    _dimension("sales_invoice_no", "销售发票号", column="sales_invoice_no", source="tb"),
                    _dimension("currency_code", "币种", column="currency_code", source="tb"),
                    _dimension("rebate_batch_no", "退税批次号", column="rebate_batch_no", source="tb"),
                    _dimension("source_system", "来源系统", column="source_system", source="tb"),
                    _dimension("doc_status", "单据状态", column="doc_status", source="tb"),
                    _dimension("enterprise_name", "企业名称", column="enterprise_name", source="e"),
                    _dimension("industry_name", "行业名称", column="industry_name", source="e"),
                ],
                metrics=[
                    _metric("customs_fob_amount_cny", "报关FOB人民币", column="customs_fob_amount_cny", source="tb", agg="sum"),
                    _metric("rebate_tax_basis_amount_cny", "退税税基金额", column="rebate_tax_basis_amount_cny", source="tb", agg="sum"),
                    _metric("non_refundable_amount_cny", "不可退税金额", column="non_refundable_amount_cny", source="tb", agg="sum"),
                    _metric("rebate_tax_amount_cny", "应退税额", column="rebate_tax_amount_cny", source="tb", agg="sum"),
                    _metric("avg_rebate_rate", "平均退税率", column="rebate_rate", source="tb", agg="avg", fmt="percent"),
                    _metric("tax_basis_line_count", "税基明细行数", expr='COUNT(*)'),
                ],
                entities=deepcopy(shared_entities),
                time=_time_with_roles(
                    "rebate_period",
                    "month",
                    ["month", "quarter", "year"],
                    default_role="rebate_period",
                    roles={
                        "rebate_period": {"field": "rebate_period", "grain": "month"},
                        "export_date": {"field": "export_date", "grain": "day", "range_mode": "date"},
                    },
                ),
                business_terms=["出口退税", "税基金额", "报关FOB", "退税率", "报关单"],
                intent_aliases=["出口退税税基明细", "退税税基口径", "税基单证链"],
                analysis_patterns=["税基追溯", "报关单定位", "detail"],
                evidence_requirements=["税基口径需返回报关单号或退税批次号", "退税分析需展示税基金额、不可退税金额和应退税额"],
            ),
            _model(
                name="fact_export_contract_discount_line",
                label="出口合同折扣明细事实",
                description="按合同明细行沉淀出口折扣、折让和返利信息，明确是否影响账面收入和退税税基。",
                kind="atomic_fact",
                domain="reconciliation",
                grain="enterprise_discount_line",
                source_table="recon_export_contract_discount_line",
                sources=[{"table": "recon_export_contract_discount_line", "alias": "ds"}, {"table": "enterprise_info", "alias": "e"}],
                joins=[{"left": "ds.taxpayer_id", "right": "e.taxpayer_id", "type": "left"}],
                dimensions=[
                    _dimension("taxpayer_id", "纳税人识别号", column="taxpayer_id", source="ds"),
                    _dimension("contract_id", "合同号", column="contract_id", source="ds"),
                    _dimension("contract_line_id", "合同明细行号", column="contract_line_id", source="ds"),
                    _dimension("discount_doc_no", "折扣单据号", column="discount_doc_no", source="ds"),
                    _dimension("discount_type_code", "折扣类型编码", column="discount_type_code", source="ds"),
                    _dimension("discount_type_name", "折扣类型", column="discount_type_name", source="ds"),
                    _dimension("discount_reason", "折扣原因", column="discount_reason", source="ds"),
                    _dimension("book_period", "账面期间", column="book_period", source="ds"),
                    _dimension("rebate_period", "税基传递期间", column="rebate_period", source="ds"),
                    _dimension("discount_effective_date", "折扣生效日期", column="effective_date", source="ds"),
                    _dimension("related_declaration_no", "关联报关单号", column="related_declaration_no", source="ds"),
                    _dimension("related_invoice_no", "关联发票号", column="related_invoice_no", source="ds"),
                    _dimension("allocation_method", "分摊方式", column="allocation_method", source="ds"),
                    _dimension("allocation_scope", "分摊范围", column="allocation_scope", source="ds"),
                    _dimension("sync_status", "同步状态", column="sync_status", source="ds"),
                    _dimension("affect_book_revenue_flag", "影响账面收入", column="affect_book_revenue_flag", source="ds"),
                    _dimension("affect_tax_basis_flag", "影响税基", column="affect_tax_basis_flag", source="ds"),
                    _dimension("source_system", "来源系统", column="source_system", source="ds"),
                    _dimension("doc_status", "单据状态", column="doc_status", source="ds"),
                    _dimension("enterprise_name", "企业名称", column="enterprise_name", source="e"),
                    _dimension("industry_name", "行业名称", column="industry_name", source="e"),
                ],
                metrics=[
                    _metric("discount_amount_cny", "折扣金额人民币", column="discount_amount_cny", source="ds", agg="sum"),
                    _metric("book_side_discount_amount_cny", "账面侧折扣金额", column="book_side_discount_amount_cny", source="ds", agg="sum"),
                    _metric("tax_side_discount_amount_cny", "税基侧折扣金额", column="tax_side_discount_amount_cny", source="ds", agg="sum"),
                    _metric(
                        "pending_pass_through_discount_amount_cny",
                        "待传递折扣金额",
                        expr='SUM("ds"."book_side_discount_amount_cny" - "ds"."tax_side_discount_amount_cny")',
                        depends_on=["book_side_discount_amount_cny", "tax_side_discount_amount_cny"],
                    ),
                    _metric("discount_doc_count", "折扣单据数", expr='COUNT(*)'),
                ],
                entities=deepcopy(shared_entities),
                time=_time_with_roles(
                    "book_period",
                    "month",
                    ["month", "quarter", "year"],
                    default_role="book_period",
                    roles={
                        "book_period": {"field": "book_period", "grain": "month"},
                        "rebate_period": {"field": "rebate_period", "grain": "month"},
                        "discount_effective_date": {"field": "effective_date", "grain": "day", "range_mode": "date"},
                    },
                ),
                business_terms=["合同折扣", "折扣记录", "折扣单", "折让", "返利", "账面侧折扣", "税基侧折扣"],
                intent_aliases=["合同折扣明细", "折扣传递明细", "出口折扣单", "合同有没有折扣", "是否有折扣单", "折扣记录查询"],
                analysis_patterns=["折扣追溯", "折扣传递跟踪", "折扣记录核对", "detail"],
                evidence_requirements=["折扣分析需返回折扣单据号或合同号", "必须说明折扣是否影响账面收入与税基"],
            ),
            _model(
                name="mart_export_rebate_reconciliation",
                label="出口退税对账主题",
                description="围绕账面可比收入、退税税基金额和合同折扣传递差异组织的主题模型，用于出口退税税账对账与差异定位。",
                kind="composite_analysis",
                domain="reconciliation",
                grain="enterprise_contract_line",
                source_table="recon_export_book_revenue_line",
                sources=[
                    {"table": "recon_export_book_revenue_line", "alias": "br"},
                    {"table": "recon_export_refund_tax_basis_line", "alias": "tb"},
                    {"table": "recon_export_contract_discount_line", "alias": "ds"},
                    {"table": "enterprise_info", "alias": "e"},
                ],
                joins=[
                    {"left": "br.contract_line_id", "right": "tb.contract_line_id", "type": "left"},
                    {"left": "br.contract_line_id", "right": "ds.contract_line_id", "type": "left"},
                    {"left": "br.taxpayer_id", "right": "e.taxpayer_id", "type": "left"},
                ],
                dimensions=[
                    _dimension("book_period", "账面期间", column="book_period", source="br"),
                    _dimension("rebate_period", "退税所属期", column="rebate_period", source="tb"),
                    _dimension("export_date", "出口日期", column="export_date", source="tb"),
                    _dimension("discount_effective_date", "折扣生效日期", column="effective_date", source="ds"),
                    _dimension("enterprise_name", "企业名称", column="enterprise_name", source="e"),
                    _dimension("industry_name", "行业名称", column="industry_name", source="e"),
                    _dimension("contract_id", "合同号", column="contract_id", source="br"),
                    _dimension("contract_line_id", "合同明细行号", column="contract_line_id", source="br"),
                    _dimension("customer_name", "客户名称", column="customer_name", source="br"),
                    _dimension("product_name", "产品名称", column="product_name", source="br"),
                    _dimension("declaration_no", "报关单号", column="declaration_no", source="br"),
                    _dimension("declaration_line_no", "报关单行号", column="declaration_line_no", source="br", dtype="number"),
                    _dimension("sales_invoice_no", "销售发票号", column="sales_invoice_no", source="br"),
                    _dimension("rebate_batch_no", "退税批次号", column="rebate_batch_no", source="tb"),
                    _dimension("discount_doc_no", "折扣单据号", column="discount_doc_no", source="ds"),
                    _dimension("discount_type_name", "折扣类型", column="discount_type_name", source="ds"),
                    _dimension("sync_status", "同步状态", column="sync_status", source="ds"),
                ],
                metrics=[
                    _metric("book_gross_revenue_cny", "账面毛收入", column="gross_revenue_amount_cny", source="br", agg="sum"),
                    _metric("book_non_basis_exclusion_amount_cny", "账面非税基扣减额", column="book_non_basis_exclusion_amount_cny", source="br", agg="sum"),
                    _metric("book_net_revenue_before_discount_cny", "折扣前账面可比收入", column="book_net_revenue_before_discount_cny", source="br", agg="sum"),
                    _metric("book_side_discount_amount_cny", "账面侧折扣金额", expr='SUM(COALESCE("ds"."book_side_discount_amount_cny", 0))'),
                    _metric(
                        "book_net_revenue_after_discount_cny",
                        "折扣后账面可比收入",
                        expr='SUM("br"."book_net_revenue_before_discount_cny") - SUM(COALESCE("ds"."book_side_discount_amount_cny", 0))',
                        depends_on=["book_net_revenue_before_discount_cny", "book_side_discount_amount_cny"],
                    ),
                    _metric("rebate_tax_basis_amount_cny", "退税税基金额", column="rebate_tax_basis_amount_cny", source="tb", agg="sum"),
                    _metric("tax_side_discount_amount_cny", "税基侧折扣金额", expr='SUM(COALESCE("ds"."tax_side_discount_amount_cny", 0))'),
                    _metric(
                        "rebate_tax_basis_after_discount_cny",
                        "折扣后税基金额",
                        expr='SUM("tb"."rebate_tax_basis_amount_cny") - SUM(COALESCE("ds"."tax_side_discount_amount_cny", 0))',
                        depends_on=["rebate_tax_basis_amount_cny", "tax_side_discount_amount_cny"],
                    ),
                    _metric("rebate_tax_amount_cny", "应退税额", column="rebate_tax_amount_cny", source="tb", agg="sum"),
                    _metric(
                        "reconciliation_gap_amount",
                        "税账对账差异金额",
                        expr='(SUM("tb"."rebate_tax_basis_amount_cny") - SUM(COALESCE("ds"."tax_side_discount_amount_cny", 0))) - (SUM("br"."book_net_revenue_before_discount_cny") - SUM(COALESCE("ds"."book_side_discount_amount_cny", 0)))',
                        depends_on=["rebate_tax_basis_after_discount_cny", "book_net_revenue_after_discount_cny"],
                    ),
                    _metric(
                        "pending_discount_gap_amount",
                        "折扣待传递差额",
                        expr='SUM(COALESCE("ds"."book_side_discount_amount_cny", 0) - COALESCE("ds"."tax_side_discount_amount_cny", 0))',
                        depends_on=["book_side_discount_amount_cny", "tax_side_discount_amount_cny"],
                    ),
                    _metric(
                        "reconciliation_gap_rate",
                        "税账差异率",
                        expr='CASE WHEN (SUM("br"."book_net_revenue_before_discount_cny") - SUM(COALESCE("ds"."book_side_discount_amount_cny", 0))) = 0 THEN 0 ELSE ((SUM("tb"."rebate_tax_basis_amount_cny") - SUM(COALESCE("ds"."tax_side_discount_amount_cny", 0))) - (SUM("br"."book_net_revenue_before_discount_cny") - SUM(COALESCE("ds"."book_side_discount_amount_cny", 0)))) / NULLIF((SUM("br"."book_net_revenue_before_discount_cny") - SUM(COALESCE("ds"."book_side_discount_amount_cny", 0))), 0) END',
                        fmt="percent",
                        depends_on=["reconciliation_gap_amount", "book_net_revenue_after_discount_cny"],
                    ),
                    _metric("discount_doc_count", "折扣单据数", expr='COUNT(DISTINCT "ds"."discount_doc_no")'),
                ],
                entities=deepcopy(shared_entities),
                time=_time_with_roles(
                    "rebate_period",
                    "month",
                    ["month", "quarter", "year"],
                    default_role="rebate_period",
                    roles={
                        "rebate_period": {"field": "rebate_period", "grain": "month"},
                        "book_period": {"field": "book_period", "grain": "month"},
                        "export_date": {"field": "export_date", "grain": "day", "range_mode": "date"},
                        "discount_effective_date": {"field": "discount_effective_date", "grain": "day", "range_mode": "date"},
                    },
                ),
                business_terms=["出口退税", "账面收入", "税基金额", "合同折扣", "报关单", "退税对账"],
                intent_aliases=["出口退税对账", "税基金额对账", "账面收入和税基金额对账", "出口退税差异分析"],
                analysis_patterns=["出口退税对账", "税基差异定位", "差异归因", "单证链下钻", "reconciliation"],
                evidence_requirements=["对账结论需同时返回账面可比收入、税基金额和差异金额", "差异归因需说明是否存在折扣待传递或报关口径差异"],
                detail_fields=[
                    _dimension("enterprise_name", "企业名称", column="enterprise_name", source="e"),
                    _dimension("contract_id", "合同号", column="contract_id", source="br"),
                    _dimension("contract_line_id", "合同明细行号", column="contract_line_id", source="br"),
                    _dimension("book_period", "账面期间", column="book_period", source="br"),
                    _dimension("rebate_period", "退税所属期", column="rebate_period", source="tb"),
                    _dimension("declaration_no", "报关单号", column="declaration_no", source="br"),
                    _dimension("sales_invoice_no", "销售发票号", column="sales_invoice_no", source="br"),
                    _dimension("customer_name", "客户名称", column="customer_name", source="br"),
                    _dimension("product_name", "产品名称", column="product_name", source="br"),
                    _dimension("discount_doc_no", "折扣单据号", column="discount_doc_no", source="ds"),
                    _dimension("discount_type_name", "折扣类型", column="discount_type_name", source="ds"),
                    _dimension("sync_status", "同步状态", column="sync_status", source="ds"),
                    _dimension("book_net_revenue_before_discount_detail", "折扣前账面可比收入", expr='"br"."book_net_revenue_before_discount_cny"', dtype="number"),
                    _dimension("book_discount_amount_detail", "账面侧折扣金额", expr='COALESCE("ds"."book_side_discount_amount_cny", 0)', dtype="number"),
                    _dimension("rebate_tax_basis_amount_detail", "退税税基金额", expr='"tb"."rebate_tax_basis_amount_cny"', dtype="number"),
                    _dimension("tax_discount_amount_detail", "税基侧折扣金额", expr='COALESCE("ds"."tax_side_discount_amount_cny", 0)', dtype="number"),
                    _dimension(
                        "reconciliation_gap_amount_detail",
                        "税账对账差异金额",
                        expr='("tb"."rebate_tax_basis_amount_cny" - COALESCE("ds"."tax_side_discount_amount_cny", 0)) - ("br"."book_net_revenue_before_discount_cny" - COALESCE("ds"."book_side_discount_amount_cny", 0))',
                        dtype="number",
                    ),
                ],
            ),
            _model(
                name="mart_export_discount_bridge",
                label="出口合同折扣传递支持主题",
                description="围绕折扣在账面收入与退税税基之间的传递状态组织的支持性主题模型，用于在出口退税对账后继续定位折扣待传递、返利待同步等二跳问题。",
                kind="composite_analysis",
                domain="reconciliation",
                grain="enterprise_discount_line",
                source_table="recon_export_contract_discount_line",
                entry_enabled=False,
                sources=[
                    {"table": "recon_export_contract_discount_line", "alias": "ds"},
                    {"table": "recon_export_book_revenue_line", "alias": "br"},
                    {"table": "recon_export_refund_tax_basis_line", "alias": "tb"},
                    {"table": "enterprise_info", "alias": "e"},
                ],
                joins=[
                    {"left": "ds.contract_line_id", "right": "br.contract_line_id", "type": "left"},
                    {"left": "ds.contract_line_id", "right": "tb.contract_line_id", "type": "left"},
                    {"left": "ds.taxpayer_id", "right": "e.taxpayer_id", "type": "left"},
                ],
                dimensions=[
                    _dimension("book_period", "账面期间", column="book_period", source="ds"),
                    _dimension("rebate_period", "税基传递期间", column="rebate_period", source="ds"),
                    _dimension("discount_effective_date", "折扣生效日期", column="effective_date", source="ds"),
                    _dimension("enterprise_name", "企业名称", column="enterprise_name", source="e"),
                    _dimension("industry_name", "行业名称", column="industry_name", source="e"),
                    _dimension("contract_id", "合同号", column="contract_id", source="ds"),
                    _dimension("contract_line_id", "合同明细行号", column="contract_line_id", source="ds"),
                    _dimension("customer_name", "客户名称", column="customer_name", source="br"),
                    _dimension("product_name", "产品名称", column="product_name", source="br"),
                    _dimension("discount_doc_no", "折扣单据号", column="discount_doc_no", source="ds"),
                    _dimension("discount_type_name", "折扣类型", column="discount_type_name", source="ds"),
                    _dimension("discount_reason", "折扣原因", column="discount_reason", source="ds"),
                    _dimension("allocation_method", "分摊方式", column="allocation_method", source="ds"),
                    _dimension("allocation_scope", "分摊范围", column="allocation_scope", source="ds"),
                    _dimension("sync_status", "同步状态", column="sync_status", source="ds"),
                    _dimension("related_declaration_no", "关联报关单号", column="related_declaration_no", source="ds"),
                    _dimension("related_invoice_no", "关联发票号", column="related_invoice_no", source="ds"),
                ],
                metrics=[
                    _metric("discount_amount_cny", "折扣金额人民币", column="discount_amount_cny", source="ds", agg="sum"),
                    _metric("book_side_discount_amount_cny", "账面侧折扣金额", column="book_side_discount_amount_cny", source="ds", agg="sum"),
                    _metric("tax_side_discount_amount_cny", "税基侧折扣金额", column="tax_side_discount_amount_cny", source="ds", agg="sum"),
                    _metric(
                        "pending_pass_through_discount_amount_cny",
                        "待传递折扣金额",
                        expr='SUM("ds"."book_side_discount_amount_cny" - "ds"."tax_side_discount_amount_cny")',
                        depends_on=["book_side_discount_amount_cny", "tax_side_discount_amount_cny"],
                    ),
                    _metric(
                        "pending_pass_through_rate",
                        "待传递折扣率",
                        expr='CASE WHEN SUM("ds"."book_side_discount_amount_cny") = 0 THEN 0 ELSE SUM("ds"."book_side_discount_amount_cny" - "ds"."tax_side_discount_amount_cny") / NULLIF(SUM("ds"."book_side_discount_amount_cny"), 0) END',
                        fmt="percent",
                        depends_on=["pending_pass_through_discount_amount_cny", "book_side_discount_amount_cny"],
                    ),
                    _metric("affected_contract_line_count", "受影响合同明细行数", expr='COUNT(DISTINCT "ds"."contract_line_id")'),
                ],
                entities=deepcopy(shared_entities),
                time=_time_with_roles(
                    "book_period",
                    "month",
                    ["month", "quarter", "year"],
                    default_role="book_period",
                    roles={
                        "book_period": {"field": "book_period", "grain": "month"},
                        "rebate_period": {"field": "rebate_period", "grain": "month"},
                        "discount_effective_date": {"field": "discount_effective_date", "grain": "day", "range_mode": "date"},
                    },
                ),
                business_terms=["合同折扣", "合同返利", "折让", "折扣传递", "折扣待传递", "返利待同步", "同步状态"],
                intent_aliases=["折扣待传递定位", "折扣传递状态", "返利待同步", "折扣传递异常"],
                analysis_patterns=["折扣待传递定位", "折扣传递状态分析", "返利待同步分析", "差异来源追踪"],
                evidence_requirements=["折扣桥接结论需返回账面侧与税基侧折扣金额", "必须说明同步状态与分摊方式"],
                detail_fields=[
                    _dimension("enterprise_name", "企业名称", column="enterprise_name", source="e"),
                    _dimension("contract_id", "合同号", column="contract_id", source="ds"),
                    _dimension("contract_line_id", "合同明细行号", column="contract_line_id", source="ds"),
                    _dimension("discount_doc_no", "折扣单据号", column="discount_doc_no", source="ds"),
                    _dimension("discount_type_name", "折扣类型", column="discount_type_name", source="ds"),
                    _dimension("discount_reason", "折扣原因", column="discount_reason", source="ds"),
                    _dimension("book_period", "账面期间", column="book_period", source="ds"),
                    _dimension("rebate_period", "税基传递期间", column="rebate_period", source="ds"),
                    _dimension("discount_effective_date", "折扣生效日期", column="effective_date", source="ds"),
                    _dimension("sync_status", "同步状态", column="sync_status", source="ds"),
                    _dimension("allocation_method", "分摊方式", column="allocation_method", source="ds"),
                    _dimension("book_side_discount_amount_detail", "账面侧折扣金额", expr='"ds"."book_side_discount_amount_cny"', dtype="number"),
                    _dimension("tax_side_discount_amount_detail", "税基侧折扣金额", expr='"ds"."tax_side_discount_amount_cny"', dtype="number"),
                    _dimension(
                        "pending_pass_through_discount_amount_detail",
                        "待传递折扣金额",
                        expr='"ds"."book_side_discount_amount_cny" - "ds"."tax_side_discount_amount_cny"',
                        dtype="number",
                    ),
                ],
            ),
        ]
    )

    return records


SEMANTIC_MODEL_RECORDS = build_semantic_model_records()
SEMANTIC_YAML_MAP = {item["name"]: item["yaml_definition"] for item in SEMANTIC_MODEL_RECORDS}


async def seed_semantic_model_assets(session: AsyncSession) -> None:
    result = await session.execute(select(SysSemanticModel))
    existing_models = {model.name: model for model in result.scalars().all()}
    active_names = {item["name"] for item in SEMANTIC_MODEL_RECORDS}

    for name, model in existing_models.items():
        if name in LEGACY_MODEL_NAMES and name not in active_names:
            model.status = "archived"

    for payload in SEMANTIC_MODEL_RECORDS:
        model = existing_models.get(payload["name"])
        if model is None:
            session.add(SysSemanticModel(**payload))
            continue
        for key, value in payload.items():
            setattr(model, key, deepcopy(value) if isinstance(value, (dict, list)) else value)

    await session.flush()
