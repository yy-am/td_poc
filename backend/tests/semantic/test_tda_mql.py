from __future__ import annotations

import pytest

from app.mock.semantic_assets import SEMANTIC_MODEL_RECORDS
from app.schemas.semantic import (
    TdaMqlAnalysisMode,
    TdaMqlDrilldown,
    TdaMqlRequest,
    TdaMqlSelectItem,
    TdaMqlTimeContext,
)
from app.semantic.catalog import extract_semantic_metadata
from app.semantic.mql import _build_semantic_query_payload, _detect_unsupported_features


def _metadata(model_name: str) -> dict:
    record = next(item for item in SEMANTIC_MODEL_RECORDS if item["name"] == model_name)
    return extract_semantic_metadata(
        name=record["name"],
        label=record["label"],
        description=record["description"],
        source_table=record["source_table"],
        model_type=record["model_type"],
        yaml_definition=record["yaml_definition"],
        status=record["status"],
    )


def test_semantic_metadata_exposes_phase1_asset_fields():
    metadata = _metadata("mart_revenue_timing_gap")

    assert metadata["relationship_graph"]
    assert metadata["metric_lineage"]
    assert metadata["detail_fields"]
    assert metadata["materialization_policy"]["mode"] == "prefer_semantic_asset"
    assert metadata["query_hints"]["supports_drilldown"] is True
    assert any(item["metric_name"] == "revenue_gap_rate" for item in metadata["metric_lineage"])


def test_semantic_metadata_exposes_new_tax_reconciliation_assets():
    metadata = _metadata("mart_cit_settlement_bridge")

    assert metadata["time"] == {"field": "tax_year", "grain": "year", "available_grains": ["year"]}
    assert metadata["query_hints"]["preferred_lane"] == "metric"
    assert any(item["metric_name"] == "effective_tax_rate" for item in metadata["metric_lineage"])
    assert any(item["name"] == "tax_amount_detail" for item in metadata["detail_fields"])


def test_export_rebate_metadata_exposes_time_roles_and_doc_chain_fields():
    metadata = _metadata("mart_export_rebate_reconciliation")

    assert metadata["time"]["default_role"] == "rebate_period"
    assert metadata["time"]["roles"]["book_period"]["field"] == "book_period"
    assert metadata["time"]["roles"]["export_date"]["range_mode"] == "date"
    assert any(item["metric_name"] == "reconciliation_gap_amount" for item in metadata["metric_lineage"])
    assert any(item["name"] == "contract_id" for item in metadata["detail_fields"])


def test_build_semantic_query_payload_supports_quarter_range():
    metadata = _metadata("mart_revenue_timing_gap")
    payload = TdaMqlRequest(
        model_name="mart_revenue_timing_gap",
        select=[TdaMqlSelectItem(metric="revenue_gap_amount")],
        group_by=["period"],
        time_context=TdaMqlTimeContext(grain="month", range="2024Q3"),
    )

    compiled = _build_semantic_query_payload(payload, metadata)

    assert compiled["metrics"] == ["revenue_gap_amount"]
    assert compiled["dimensions"] == ["period"]
    assert compiled["filters"][-1] == {
        "field": "period",
        "op": "in",
        "value": ["2024-07", "2024-08", "2024-09"],
    }


def test_build_semantic_query_payload_supports_year_range_for_year_grain_model():
    metadata = _metadata("mart_cit_settlement_bridge")
    payload = TdaMqlRequest(
        model_name="mart_cit_settlement_bridge",
        select=[TdaMqlSelectItem(metric="tax_amount")],
        group_by=["tax_year"],
        time_context=TdaMqlTimeContext(grain="year", range="2024"),
    )

    compiled = _build_semantic_query_payload(payload, metadata)

    assert compiled["metrics"] == ["tax_amount"]
    assert compiled["dimensions"] == ["tax_year"]
    assert compiled["filters"][-1] == {
        "field": "tax_year",
        "op": "eq",
        "value": 2024,
    }


def test_build_semantic_query_payload_uses_detail_fields_for_drilldown():
    metadata = _metadata("mart_revenue_timing_gap")
    payload = TdaMqlRequest(
        model_name="mart_revenue_timing_gap",
        drilldown=TdaMqlDrilldown(enabled=True),
    )

    compiled = _build_semantic_query_payload(payload, metadata)

    assert compiled["metrics"] == []
    assert "diff_explanation" in compiled["dimensions"]
    assert "revenue_gap_amount_detail" in compiled["dimensions"]


def test_build_semantic_query_payload_prefers_explicit_detail_fields_for_drilldown():
    metadata = _metadata("mart_revenue_timing_gap")
    payload = TdaMqlRequest(
        model_name="mart_revenue_timing_gap",
        drilldown=TdaMqlDrilldown(
            enabled=True,
            target="revenue_gap_amount",
            detail_fields=["enterprise_name", "diff_explanation"],
            limit=7,
        ),
    )

    compiled = _build_semantic_query_payload(payload, metadata)

    assert compiled["metrics"] == []
    assert compiled["dimensions"] == ["enterprise_name", "diff_explanation"]
    assert compiled["limit"] == 7


def test_build_semantic_query_payload_supports_time_role_for_export_rebate_period():
    metadata = _metadata("mart_export_rebate_reconciliation")
    payload = TdaMqlRequest(
        model_name="mart_export_rebate_reconciliation",
        select=[TdaMqlSelectItem(metric="reconciliation_gap_amount")],
        group_by=["contract_id"],
        time_context=TdaMqlTimeContext(grain="month", range="2024-08", role="rebate_period"),
    )

    compiled = _build_semantic_query_payload(payload, metadata)

    assert compiled["filters"][-1] == {
        "field": "rebate_period",
        "op": "eq",
        "value": "2024-08",
    }


def test_build_semantic_query_payload_supports_time_role_for_export_book_period():
    metadata = _metadata("mart_export_rebate_reconciliation")
    payload = TdaMqlRequest(
        model_name="mart_export_rebate_reconciliation",
        select=[TdaMqlSelectItem(metric="reconciliation_gap_amount")],
        group_by=["contract_id"],
        time_context=TdaMqlTimeContext(grain="month", range="2024Q3", role="book_period"),
    )

    compiled = _build_semantic_query_payload(payload, metadata)

    assert compiled["filters"][-1] == {
        "field": "book_period",
        "op": "in",
        "value": ["2024-07", "2024-08", "2024-09"],
    }


def test_build_semantic_query_payload_supports_date_role_for_export_date():
    metadata = _metadata("mart_export_rebate_reconciliation")
    payload = TdaMqlRequest(
        model_name="mart_export_rebate_reconciliation",
        select=[TdaMqlSelectItem(metric="rebate_tax_basis_amount_cny")],
        group_by=["contract_id"],
        time_context=TdaMqlTimeContext(grain="month", range="2024-08", role="export_date"),
    )

    compiled = _build_semantic_query_payload(payload, metadata)

    assert compiled["filters"][-1] == {
        "field": "export_date",
        "op": "between",
        "value": ["2024-08-01", "2024-08-31"],
    }


def test_tda_mql_request_preserves_compare_and_drilldown_schema_fields():
    payload = TdaMqlRequest(
        model_name="mart_revenue_timing_gap",
        select=[TdaMqlSelectItem(metric="revenue_gap_amount")],
        time_context=TdaMqlTimeContext(grain="month", range="2024Q3", compare="YoY", role="tax_period"),
        analysis_mode=TdaMqlAnalysisMode(type="comparison", attribution=False, top_k=5),
        drilldown=TdaMqlDrilldown(
            enabled=True,
            target="revenue_gap_amount",
            detail_fields=["diff_explanation"],
            limit=10,
        ),
    )

    assert payload.time_context is not None
    assert payload.time_context.compare == "YoY"
    assert payload.time_context.role == "tax_period"
    assert payload.analysis_mode is not None
    assert payload.analysis_mode.type == "comparison"
    assert payload.analysis_mode.top_k == 5
    assert payload.drilldown is not None
    assert payload.drilldown.enabled is True
    assert payload.drilldown.target == "revenue_gap_amount"
    assert payload.drilldown.detail_fields == ["diff_explanation"]
    assert payload.drilldown.limit == 10


def test_compare_requests_will_stop_being_flagged_unsupported_once_p1_lands():
    payload = TdaMqlRequest(
        model_name="mart_revenue_timing_gap",
        select=[TdaMqlSelectItem(metric="revenue_gap_amount")],
        time_context=TdaMqlTimeContext(grain="month", range="2024Q3", compare="YoY"),
    )

    unsupported = _detect_unsupported_features(payload)

    assert "time_context.compare" not in unsupported


def test_detect_unsupported_features_flags_attribution_only():
    payload = TdaMqlRequest(
        model_name="mart_revenue_timing_gap",
        select=[TdaMqlSelectItem(metric="revenue_gap_amount")],
        time_context=TdaMqlTimeContext(grain="month", range="2024Q3", compare="YoY"),
        analysis_mode=TdaMqlAnalysisMode(type="attribution", attribution=True),
    )

    unsupported = _detect_unsupported_features(payload)

    assert "analysis_mode.attribution" in unsupported
    assert "analysis_mode.type=attribution" in unsupported
