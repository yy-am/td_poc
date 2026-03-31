from __future__ import annotations

from app.agent.semantic_grounding import (
    _extract_model_metadata,
    _merge_company_fragments,
    _merge_query_keywords,
    _score_model,
)
from app.agent.runtime_context import _collect_query_keywords
from app.mock.semantic_assets import SEMANTIC_MODEL_RECORDS


def test_extract_model_metadata_reads_semantic_yaml_fields():
    metadata = _extract_model_metadata(
        name="reconciliation_dashboard",
        label="Revenue Reconciliation",
        description="Compares declared and booked revenue",
        source_table="recon_revenue",
        yaml_definition="""
name: reconciliation_dashboard
business_terms: [revenue gap, reconciliation]
intent_aliases: [compare declared revenue]
analysis_patterns: [compare, reconciliation]
time:
  default_field: period
entities:
  enterprise:
    id_field: taxpayer_id
dimensions:
  - name: period
    label: Period
    column: period
  - enterprise_name
metrics:
  - name: vat_declared_revenue
    label: Declared Revenue
    column: declared_revenue
    agg: sum
  - booked_revenue
""",
        status="active",
    )

    assert metadata["has_yaml_definition"] is True
    assert metadata["recommended_tool"] == "semantic_query"
    assert metadata["business_terms"] == ["revenue gap", "reconciliation"]
    assert metadata["intent_aliases"] == ["compare declared revenue"]
    assert metadata["analysis_patterns"] == ["compare", "reconciliation"]
    assert metadata["time"] == {"default_field": "period"}
    assert metadata["entities"] == {"enterprise": {"id_field": "taxpayer_id"}}
    assert metadata["dimensions"] == ["period", "Period", "enterprise_name"]
    assert metadata["metrics"] == [
        "vat_declared_revenue",
        "Declared Revenue",
        "declared_revenue",
        "booked_revenue",
    ]


def test_extract_model_metadata_can_recommend_mql_query_for_metric_lane():
    metadata = _extract_model_metadata(
        name="mart_revenue_timing_gap",
        label="收入错期诊断主题",
        description="Composite analysis model",
        source_table="recon_revenue_comparison",
        model_type="metric",
        yaml_definition="""
name: mart_revenue_timing_gap
kind: composite_analysis
sources:
  - table: recon_revenue_comparison
    alias: rc
dimensions:
  - period
metrics:
  - name: revenue_gap_amount
    column: vat_vs_acct_diff
    agg: sum
query_hints:
  preferred_lane: metric
""",
        status="active",
    )

    assert metadata["recommended_tool"] == "mql_query"


def test_extract_model_metadata_returns_safe_defaults_for_invalid_yaml():
    metadata = _extract_model_metadata(
        name="broken_model",
        label="Broken",
        description="Invalid yaml",
        source_table="broken_table",
        yaml_definition=": not valid yaml",
        status="active",
    )

    assert metadata["has_yaml_definition"] is True
    assert metadata["dimensions"] == []
    assert metadata["metrics"] == []
    assert metadata["business_terms"] == []


def test_score_model_boosts_candidate_model_metrics_dimensions_and_patterns():
    model = {
        "name": "reconciliation_dashboard",
        "label": "Revenue Reconciliation",
        "description": "Revenue gap model",
        "source_table": "recon_revenue",
        "business_terms": [],
        "intent_aliases": [],
        "dimensions": ["period"],
        "metrics": ["revenue_gap"],
        "analysis_patterns": ["compare"],
    }

    score, matched = _score_model(
        "Compare revenue gap by month",
        model,
        ["revenue_gap"],
        {
            "query_mode": "analysis",
            "candidate_models": ["reconciliation_dashboard"],
            "metrics": ["revenue_gap"],
            "dimensions": ["period"],
        },
    )

    assert score == 24
    assert matched == ["revenue_gap", "compare"]


def test_merge_query_keywords_includes_understanding_fields_without_duplicates():
    keywords = _merge_query_keywords(
        "Show revenue_gap by month",
        {
            "metrics": ["revenue_gap", "revenue_gap"],
            "dimensions": ["period"],
            "candidate_models": ["reconciliation_dashboard"],
            "entities": {"enterprise_names": ["Acme Corp", "Acme Corp"]},
            "business_goal": "Find the monthly revenue gap",
        },
    )

    assert "revenue_gap" in keywords
    assert "period" in keywords
    assert "reconciliation_dashboard" in keywords
    assert "Acme Corp" in keywords
    assert "Find the monthly revenue gap" in keywords
    assert keywords.count("revenue_gap") == 1


def test_merge_company_fragments_appends_understanding_enterprise_names():
    fragments = _merge_company_fragments(
        "",
        {"entities": {"enterprise_names": ["Acme Corp", "Acme Corp", "Beta LLC"]}},
    )

    assert fragments == ["Acme Corp", "Beta LLC"]


def _asset_metadata(name: str) -> dict:
    record = next(item for item in SEMANTIC_MODEL_RECORDS if item["name"] == name)
    return _extract_model_metadata(
        name=record["name"],
        label=record["label"],
        description=record["description"],
        source_table=record["source_table"],
        model_type=record["model_type"],
        yaml_definition=record["yaml_definition"],
        status=record["status"],
    )


def test_collect_query_keywords_captures_new_tax_bridge_and_diagnostic_terms():
    keywords = _collect_query_keywords(
        "查看华兴科技 2024 年所得税汇算清缴桥接，重点看应纳税所得额和应补退税额；"
        "再看增值税申报诊断中的进项、销项和转出对税负的影响"
    )

    for term in ("汇算清缴", "桥接", "应纳税所得额", "应补退税额", "进项", "销项", "转出", "税负", "诊断"):
        assert term in keywords


def test_score_model_matches_cit_bridge_aliases_and_business_terms():
    query = "查看华兴科技 2024 年所得税汇算清缴桥接，重点看应纳税所得额和应补退税额"
    metadata = _asset_metadata("mart_cit_settlement_bridge")

    score, matched = _score_model(query, metadata, _collect_query_keywords(query), None)

    assert score >= 18
    assert "汇算清缴桥接" in matched
    assert "应纳税所得额" in matched
    assert "应补退税额" in matched


def test_score_model_matches_vat_diagnostic_aliases_and_terms():
    query = "查看华兴科技 2024Q3 增值税申报诊断，分析进项、销项和转出对税负的影响"
    metadata = _asset_metadata("mart_vat_declaration_diagnostics")

    score, matched = _score_model(query, metadata, _collect_query_keywords(query), None)

    assert score >= 18
    assert "增值税申报诊断" in matched
    assert "进项" in matched
    assert "销项" in matched
    assert "转出" in matched

def test_score_model_matches_export_rebate_reconciliation_terms():
    query = "查看明达制造 2024年8月出口退税对账，重点看税基金额和合同折扣导致的差异"
    metadata = _asset_metadata("mart_export_rebate_reconciliation")

    score, matched = _score_model(query, metadata, _collect_query_keywords(query), None)

    assert score >= 18
    assert "出口退税对账" in matched
    assert "税基金额" in matched
    assert "合同折扣" in matched


def test_score_model_matches_export_discount_bridge_terms():
    query = "查看天和医药 2024年10月折扣待传递定位，分析返利待同步和折扣传递状态"
    metadata = _asset_metadata("mart_export_discount_bridge")

    score, matched = _score_model(query, metadata, _collect_query_keywords(query), None)

    assert score >= 14
    assert "折扣待传递定位" in matched
    assert "折扣待传递" in matched


def test_export_discount_bridge_is_supporting_model_not_primary_entry():
    metadata = _asset_metadata("mart_export_discount_bridge")

    assert metadata["entry_enabled"] is False


def test_reconciliation_query_prefers_export_rebate_model_over_discount_bridge():
    query = "分析明达制造 2024年8月出口退税账面收入与税基金额差异，定位涉及合同号并判断是否存在合同折扣影响"
    keywords = _collect_query_keywords(query)
    understanding = {"query_mode": "reconciliation"}

    rebate_score, _ = _score_model(
        query,
        _asset_metadata("mart_export_rebate_reconciliation"),
        keywords,
        understanding,
    )
    discount_score, _ = _score_model(
        query,
        _asset_metadata("mart_export_discount_bridge"),
        keywords,
        understanding,
    )

    assert rebate_score > discount_score


def test_discount_record_query_prefers_discount_fact_over_supporting_bridge():
    query = "查看明达制造 2024年8月这些合同是否有折扣单，返回合同号、折扣单号、折扣金额和同步状态"
    keywords = _collect_query_keywords(query)
    understanding = {"query_mode": "fact_query"}

    fact_score, matched = _score_model(
        query,
        _asset_metadata("fact_export_contract_discount_line"),
        keywords,
        understanding,
    )
    bridge_score, _ = _score_model(
        query,
        _asset_metadata("mart_export_discount_bridge"),
        keywords,
        understanding,
    )

    assert fact_score > bridge_score
    assert "是否有折扣单" in matched
