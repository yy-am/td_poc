from __future__ import annotations

import json

from app.agent.planner_agent_v2 import PlannerAgent


def test_enrich_plan_graph_promotes_metric_lane_model_to_mql_query():
    agent = PlannerAgent(llm=None)
    plan_graph = {
        "nodes": [
            {
                "id": "n1",
                "title": "分析收入差异",
                "detail": "按月看收入差异",
                "kind": "analysis",
                "tool_hints": ["semantic_query"],
                "semantic_binding": {},
            }
        ]
    }
    runtime_context = {
        "query_mode": "reconciliation",
        "period_hints": {
            "year": 2024,
            "quarter": 3,
            "periods": ["2024-07", "2024-08", "2024-09"],
        },
        "enterprise_candidates": [
            {"enterprise_name": "华兴科技有限公司", "taxpayer_id": "91310000123456789X"}
        ],
        "understanding_result": {
            "semantic_scope": {
                "entity_models": ["dim_enterprise"],
                "atomic_models": [],
                "composite_models": ["mart_revenue_timing_gap"],
            },
            "dimensions": ["period"],
            "metrics": ["revenue_gap_amount"],
            "entities": {"enterprise_names": ["华兴科技有限公司"]},
        },
        "relevant_models": [
            {
                "name": "mart_revenue_timing_gap",
                "dimensions": ["period", "enterprise_name", "diff_explanation"],
                "metrics": ["revenue_gap_amount", "revenue_gap_rate"],
                "time": {"field": "period", "grain": "month"},
                "semantic_kind": "composite_analysis",
                "query_hints": {"preferred_lane": "metric"},
                "recommended_tool": "mql_query",
                "fallback_policy": "fallback_to_atomic_fact",
            }
        ],
    }

    enriched = agent._enrich_plan_graph_with_runtime_semantics(plan_graph, runtime_context)
    node = enriched["nodes"][0]

    assert node["tool_hints"] == ["mql_query"]
    assert node["semantic_binding"]["entry_model"] == "mart_revenue_timing_gap"
    assert node["semantic_binding"]["query_language"] == "tda_mql"
    assert node["semantic_binding"]["metrics"] == ["revenue_gap_amount"]
    assert node["semantic_binding"]["dimensions"] == ["period"]
    assert node["semantic_binding"]["entity_filters"] == {"enterprise_name": ["华兴科技有限公司"]}
    assert node["semantic_binding"]["time_context"] == {"grain": "month", "range": "2024Q3"}


def test_enrich_plan_graph_keeps_semantic_query_for_atomic_model():
    agent = PlannerAgent(llm=None)
    plan_graph = {
        "nodes": [
            {
                "id": "n1",
                "title": "查询增值税申报",
                "detail": "提取申报税额",
                "kind": "query",
                "tool_hints": [],
                "semantic_binding": {},
            }
        ]
    }
    runtime_context = {
        "query_mode": "fact_query",
        "period_hints": {"year": 2024, "quarter": None, "periods": ["2024-08"]},
        "enterprise_candidates": [],
        "understanding_result": {
            "semantic_scope": {
                "entity_models": [],
                "atomic_models": ["fact_vat_declaration"],
                "composite_models": [],
            },
            "dimensions": ["tax_period"],
            "metrics": ["tax_payable"],
            "entities": {},
        },
        "relevant_models": [
            {
                "name": "fact_vat_declaration",
                "dimensions": ["tax_period", "enterprise_name"],
                "metrics": ["tax_payable", "output_tax_amount"],
                "time": {"field": "tax_period", "grain": "month"},
                "semantic_kind": "atomic_fact",
                "query_hints": {"preferred_lane": "detail"},
                "recommended_tool": "semantic_query",
                "fallback_policy": "fallback_to_sql",
            }
        ],
    }

    enriched = agent._enrich_plan_graph_with_runtime_semantics(plan_graph, runtime_context)
    node = enriched["nodes"][0]

    assert node["tool_hints"] == ["semantic_query"]
    assert node["semantic_binding"]["entry_model"] == "fact_vat_declaration"
    assert node["semantic_binding"]["query_language"] == ""
    assert node["semantic_binding"]["grain"] == "month"


def test_build_prompt_payload_compacts_runtime_context_and_understanding():
    agent = PlannerAgent(llm=None)
    runtime_context = {
        "query_mode": "analysis",
        "classification_confidence": "low",
        "matched_keywords": ["对账"],
        "all_query_keywords": ["对账", "税务", "收入差异"],
        "period_hints": {"year": 2024, "quarter": 3, "periods": ["2024-07", "2024-08", "2024-09"]},
        "company_fragments": ["华兴科技"],
        "enterprise_candidates": [
            {"enterprise_name": "华兴科技有限公司", "taxpayer_id": "91310000123456789X", "unused": "x"}
        ],
        "relevant_models": [
            {
                "name": "mart_revenue_reconciliation",
                "label": "收入对账主题",
                "description": "围绕税务申报收入与会计账面收入差异组织的主题模型。",
                "semantic_kind": "composite_analysis",
                "semantic_domain": "reconciliation",
                "semantic_grain": "enterprise_month",
                "recommended_tool": "mql_query",
                "fallback_policy": "fallback_to_atomic_fact",
                "supports_entity_resolution": True,
                "business_terms": ["收入对账", "税会差异"],
                "intent_aliases": ["收入差异"],
                "analysis_patterns": ["差异归因"],
                "dimensions": ["period", "enterprise_name", "diff_explanation"],
                "metrics": ["vat_declared_revenue", "acct_book_revenue", "vat_vs_acct_diff"],
                "time": {"field": "period", "grain": "month", "available_grains": ["month", "quarter", "year"]},
                "query_hints": {"preferred_lane": "metric", "supports_drilldown": True},
                "metric_lineage": [{"metric_name": "vat_vs_acct_diff", "depends_on": ["vat_declared_revenue"]}],
                "detail_fields": [{"name": "diff_explanation"}],
                "relationship_graph": [{"source": "a", "target": "b"}],
            }
        ],
        "relevant_tables": ["recon_revenue_comparison"],
        "relevant_table_schemas": [
            {
                "table_name": "recon_revenue_comparison",
                "columns": [{"name": "period", "type": "VARCHAR"}, {"name": "vat_vs_acct_diff", "type": "NUMERIC"}],
                "has_taxpayer_id": True,
                "has_enterprise_name": False,
                "has_period": True,
            }
        ],
        "execution_guidance": ["优先使用语义资产"],
        "understanding_result": {
            "query_mode": "analysis",
            "intent_summary": "分析收入差异",
            "business_goal": "定位税会收入差异",
            "entities": {"enterprise_names": ["华兴科技有限公司"]},
            "semantic_scope": {"composite_models": ["mart_revenue_reconciliation"]},
            "dimensions": ["period"],
            "metrics": ["vat_vs_acct_diff"],
            "required_evidence": ["差异说明"],
            "resolution_requirements": ["Resolve enterprise_name to taxpayer_id"],
            "candidate_models": ["mart_revenue_reconciliation"],
            "ambiguities": [],
            "confidence": "medium",
        },
    }

    payload = agent._build_prompt_payload(
        user_query="分析华兴科技 2024Q3 税会收入差异",
        conversation_history=[],
        runtime_context=runtime_context,
        understanding_result=runtime_context["understanding_result"],
    )

    compact_model = payload["runtime_context"]["relevant_models"][0]
    assert compact_model["name"] == "mart_revenue_reconciliation"
    assert "metric_lineage" not in compact_model
    assert compact_model["detail_fields"] == ["diff_explanation"]
    assert "relationship_graph" not in compact_model
    assert payload["planning_seed"]["entry_model"] == "mart_revenue_reconciliation"
    assert payload["planning_seed"]["query_language"] == "tda_mql"
    assert payload["planning_seed"]["time_context"] == {"grain": "month", "range": "2024Q3"}

    compact_len = len(json.dumps(payload, ensure_ascii=False))
    original_len = len(
        json.dumps(
            {
                "user_query": "分析华兴科技 2024Q3 税会收入差异",
                "conversation_history": [],
                "runtime_context": runtime_context,
                "understanding_result": runtime_context["understanding_result"],
            },
            ensure_ascii=False,
        )
    )
    assert compact_len < original_len


def test_infer_binding_seed_matches_query_terms_without_default_field_expansion():
    agent = PlannerAgent(llm=None)
    runtime_context = {
        "query_mode": "reconciliation",
        "period_hints": {"year": 2024, "quarter": None, "periods": ["2024-08"]},
        "enterprise_candidates": [{"enterprise_name": "明达制造", "taxpayer_id": "913100001"}],
        "understanding_result": {
            "semantic_scope": {
                "entity_models": ["dim_enterprise"],
                "atomic_models": [],
                "composite_models": ["mart_export_rebate_reconciliation"],
            },
            "dimensions": [],
            "metrics": [],
            "entities": {"enterprise_names": ["明达制造"]},
        },
        "relevant_models": [
            {
                "name": "mart_export_rebate_reconciliation",
                "dimension_terms": [
                    {"name": "rebate_period", "label": "退税所属期"},
                    {"name": "contract_id", "label": "合同号"},
                    {"name": "declaration_no", "label": "报关单号"},
                    {"name": "discount_doc_no", "label": "折扣单据号"},
                    {"name": "sync_status", "label": "同步状态"},
                    {"name": "industry_name", "label": "行业名称"},
                ],
                "metric_terms": [
                    {"name": "book_net_revenue_after_discount_cny", "label": "折扣后账面可比收入"},
                    {"name": "rebate_tax_basis_after_discount_cny", "label": "折扣后税基金额"},
                    {"name": "reconciliation_gap_amount", "label": "税账对账差异金额"},
                    {"name": "discount_doc_count", "label": "折扣单据数"},
                ],
                "time": {"field": "rebate_period", "grain": "month"},
                "semantic_kind": "composite_analysis",
                "query_hints": {"preferred_lane": "metric"},
                "recommended_tool": "mql_query",
                "fallback_policy": "fallback_to_atomic_fact",
            }
        ],
    }

    seed = agent._infer_binding_seed(
        runtime_context,
        "分析明达制造2024年8月出口退税账面收入与税基金额差异，按退税所属期统计，并下钻到合同号和报关单号，返回合同号、报关单号、折扣单号、账面收入、税基金额、差异金额和同步状态。",
    )

    assert seed["metrics"] == [
        "reconciliation_gap_amount",
        "rebate_tax_basis_after_discount_cny",
        "book_net_revenue_after_discount_cny",
    ]
    assert set(seed["dimensions"]) >= {
        "rebate_period",
        "contract_id",
        "declaration_no",
        "discount_doc_no",
        "sync_status",
    }
    assert len(seed["dimensions"]) <= 5
    assert "industry_name" not in seed["dimensions"]


def test_infer_binding_seed_enables_drilldown_only_for_explicit_drilldown_query():
    agent = PlannerAgent(llm=None)
    runtime_context = {
        "query_mode": "reconciliation",
        "period_hints": {"periods": ["2024-08"]},
        "enterprise_candidates": [{"enterprise_name": "明达制造", "taxpayer_id": "913100001"}],
        "understanding_result": {
            "semantic_scope": {
                "entity_models": ["dim_enterprise"],
                "atomic_models": [],
                "composite_models": ["mart_export_rebate_reconciliation"],
            },
            "dimensions": [],
            "metrics": [],
            "entities": {"enterprise_names": ["明达制造"]},
        },
        "relevant_models": [
            {
                "name": "mart_export_rebate_reconciliation",
                "detail_fields": [
                    {"name": "contract_id", "label": "合同号"},
                    {"name": "declaration_no", "label": "报关单号"},
                    {"name": "discount_doc_no", "label": "折扣单号"},
                    {"name": "sync_status", "label": "同步状态"},
                ],
                "time": {"field": "rebate_period", "grain": "month"},
                "semantic_kind": "composite_analysis",
                "query_hints": {"preferred_lane": "metric", "supports_drilldown": True},
                "recommended_tool": "mql_query",
                "fallback_policy": "fallback_to_atomic_fact",
            }
        ],
    }

    drilldown_seed = agent._infer_binding_seed(
        runtime_context,
        "分析明达制造2024年8月出口退税差异，下钻到合同号和报关单号，并返回明细字段",
    )
    non_drilldown_seed = agent._infer_binding_seed(
        runtime_context,
        "分析明达制造2024年8月出口退税差异",
    )

    assert drilldown_seed["drilldown"]["enabled"] is True
    assert set(drilldown_seed["drilldown"]["detail_fields"]) >= {"contract_id", "declaration_no"}
    assert non_drilldown_seed["drilldown"] == {}


def test_enrich_plan_graph_propagates_explicit_drilldown_seed_to_query_node():
    agent = PlannerAgent(llm=None)
    plan_graph = {
        "nodes": [
            {
                "id": "n1",
                "title": "定位出口退税差异明细",
                "detail": "查询存在差异的合同并下钻返回明细字段",
                "kind": "query",
                "tool_hints": ["mql_query"],
                "semantic_binding": {},
            }
        ]
    }
    runtime_context = {
        "query_mode": "reconciliation",
        "period_hints": {"periods": ["2024-08"]},
        "enterprise_candidates": [{"enterprise_name": "明达制造", "taxpayer_id": "913100001"}],
        "understanding_result": {
            "semantic_scope": {
                "entity_models": ["dim_enterprise"],
                "atomic_models": [],
                "composite_models": ["mart_export_rebate_reconciliation"],
            },
            "dimensions": [],
            "metrics": ["reconciliation_gap_amount"],
            "entities": {"enterprise_names": ["明达制造"]},
        },
        "relevant_models": [
            {
                "name": "mart_export_rebate_reconciliation",
                "dimensions": ["rebate_period", "contract_id", "declaration_no"],
                "metrics": ["reconciliation_gap_amount"],
                "detail_fields": [
                    {"name": "contract_id", "label": "合同号"},
                    {"name": "declaration_no", "label": "报关单号"},
                    {"name": "discount_doc_no", "label": "折扣单号"},
                    {"name": "sync_status", "label": "同步状态"},
                ],
                "time": {"field": "rebate_period", "grain": "month"},
                "semantic_kind": "composite_analysis",
                "query_hints": {"preferred_lane": "metric", "supports_drilldown": True},
                "recommended_tool": "mql_query",
                "fallback_policy": "fallback_to_atomic_fact",
            }
        ],
    }

    enriched = agent._enrich_plan_graph_with_runtime_semantics(
        plan_graph,
        runtime_context,
        "分析明达制造2024年8月出口退税差异，下钻到合同号和报关单号，并返回明细字段",
    )
    binding = enriched["nodes"][0]["semantic_binding"]

    assert binding["drilldown"]["enabled"] is True
    assert binding["analysis_mode"]["kind"] == "drilldown"
    assert set(binding["drilldown"]["detail_fields"]) >= {"contract_id", "declaration_no"}
