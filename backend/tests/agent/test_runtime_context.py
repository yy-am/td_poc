from __future__ import annotations

import pytest

from app.agent.runtime_context import (
    _merge_period_hints,
    build_runtime_context,
    build_runtime_status_text,
    extract_period_hints,
    validate_plan_graph,
)


def test_extract_period_hints_expands_year_and_quarter():
    hints = extract_period_hints("Compare Q3 2024 revenue")

    assert hints["year"] == 2024
    assert hints["quarter"] == 3
    assert hints["periods"] == ["2024-07", "2024-08", "2024-09"]


def test_merge_period_hints_keeps_existing_order_and_deduplicates():
    merged = _merge_period_hints(
        {"year": 2024, "quarter": 3, "periods": ["2024-07", "2024-08"]},
        {"entities": {"periods": ["2024-08", "2024-09", ""]}},
    )

    assert merged == {
        "year": 2024,
        "quarter": 3,
        "periods": ["2024-07", "2024-08", "2024-09"],
    }


@pytest.mark.asyncio
async def test_build_runtime_context_uses_understanding_and_grounding_without_db():
    understanding_result = {
        "query_mode": "reconciliation",
        "confidence": "high",
        "intent_summary": "Compare declared and booked revenue",
        "candidate_models": ["reconciliation_dashboard"],
        "entities": {
            "enterprise_names": ["Acme Corp"],
            "periods": ["2024-08"],
        },
        "metrics": ["vat_vs_acct_diff"],
        "dimensions": ["period"],
        "ambiguities": ["Need tax type if multiple returns exist"],
    }
    semantic_grounding = {
        "candidate_models": [
            {
                "name": "reconciliation_dashboard",
                "label": "Revenue Reconciliation",
                "source_table": "recon_revenue",
                "has_yaml_definition": True,
                "recommended_tool": "semantic_query",
                "score": 12,
            }
        ],
        "relevant_tables": ["recon_revenue", "enterprise_info"],
        "relevant_table_schemas": [
            {
                "table_name": "recon_revenue",
                "columns": [{"name": "taxpayer_id", "type": "TEXT"}],
                "has_taxpayer_id": True,
                "has_enterprise_name": False,
                "has_period": True,
            }
        ],
        "enterprise_candidates": [{"enterprise_name": "Acme Corp", "taxpayer_id": "9137"}],
        "query_keywords": ["revenue_gap"],
        "company_fragments": ["Acme Corp"],
    }

    context = await build_runtime_context(
        "Compare Acme Corp Q3 2024 revenue",
        understanding_result=understanding_result,
        semantic_grounding=semantic_grounding,
    )

    assert context["query_mode"] == "reconciliation"
    assert context["classification_confidence"] == "high"
    assert context["period_hints"]["periods"] == ["2024-07", "2024-08", "2024-09"]
    assert "vat_vs_acct_diff" in context["all_query_keywords"]
    assert "revenue_gap" in context["all_query_keywords"]
    assert "Acme Corp" in context["company_fragments"]
    assert context["relevant_models"] == semantic_grounding["candidate_models"]
    assert context["semantic_grounding"] == semantic_grounding
    assert context["understanding_result"] == understanding_result
    assert any(
        "reconciliation_dashboard" in guidance
        for guidance in context["execution_guidance"]
    )


def test_validate_plan_graph_flags_missing_semantic_binding_for_analysis():
    runtime_context = {
        "query_mode": "analysis",
        "relevant_models": [
            {"name": "reconciliation_dashboard", "has_yaml_definition": True}
        ],
        "understanding_result": {},
    }
    plan_graph = {
        "title": "Revenue analysis",
        "summary": "Analyze the gap",
        "nodes": [
            {
                "id": "n1",
                "title": "Query revenue facts",
                "detail": "Fetch facts",
                "kind": "query",
                "tool_hints": ["semantic_query"],
            }
        ],
    }

    issues = validate_plan_graph(plan_graph, runtime_context)

    assert any("semantic_binding" in issue for issue in issues)


def test_validate_plan_graph_flags_metadata_question_planned_as_analysis():
    runtime_context = {
        "query_mode": "metadata",
        "relevant_models": [],
        "understanding_result": {},
    }
    plan_graph = {
        "nodes": [
            {
                "id": "n1",
                "title": "Analyze revenue trend",
                "detail": "Use charts",
                "kind": "analysis",
                "tool_hints": ["chart_generator"],
            }
        ]
    }

    issues = validate_plan_graph(plan_graph, runtime_context)

    assert len(issues) == 1


def test_validate_plan_graph_flags_model_mismatch_against_understanding_result():
    runtime_context = {
        "query_mode": "fact_query",
        "relevant_models": [
            {"name": "recommended_model", "has_yaml_definition": True}
        ],
        "understanding_result": {
            "candidate_models": ["recommended_model"]
        },
    }
    plan_graph = {
        "nodes": [
            {
                "id": "n1",
                "title": "Query data",
                "detail": "Use a different model",
                "kind": "query",
                "tool_hints": ["semantic_query"],
                "semantic_binding": {"models": ["different_model"]},
            }
        ]
    }

    issues = validate_plan_graph(plan_graph, runtime_context)

    assert len(issues) == 1


def test_build_runtime_status_text_surfaces_inserted_context_fields():
    status_text = build_runtime_status_text(
        {
            "query_mode": "analysis",
            "understanding_result": {
                "intent_summary": "Compare declared and booked revenue",
                "ambiguities": ["Need exact tax type"],
            },
            "enterprise_candidates": [{"enterprise_name": "Acme Corp"}],
            "period_hints": {"periods": ["2024-07", "2024-08"]},
            "relevant_models": [
                {
                    "label": "Revenue Reconciliation",
                    "score": 12,
                    "recommended_tool": "semantic_query",
                }
            ],
        }
    )

    assert "Compare declared and booked revenue" in status_text
    assert "Acme Corp" in status_text
    assert "2024-07" in status_text
    assert "Revenue Reconciliation" in status_text
    assert "Need exact tax type" in status_text
