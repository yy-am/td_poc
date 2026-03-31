from __future__ import annotations

from types import SimpleNamespace

import pytest

import app.agent.orchestrator as orchestrator_module
from app.agent.executor_agent_v2 import ExecutionResult
from app.agent.orchestrator import MultiAgentOrchestrator, _build_semantic_binding_stage_payload
from app.agent.reviewer_agent_v2 import ReviewResult, SynthesisResult
from app.semantic.compiler_v2 import SemanticDefinitionError


class _DummyUnderstandingResult:
    def __init__(self, payload: dict):
        self._payload = payload

    def to_dict(self) -> dict:
        return dict(self._payload)


class _FakeUnderstandingAgent:
    async def understand(self, user_query, conversation_history, semantic_grounding):
        return _DummyUnderstandingResult(
            {
                "query_mode": "reconciliation",
                "intent_summary": "分析税会收入差异",
                "business_goal": "确认差异并输出结论",
                "entities": {"enterprise_names": ["华兴科技有限公司"]},
                "semantic_scope": {
                    "entity_models": ["dim_enterprise"],
                    "atomic_models": [],
                    "composite_models": ["mart_revenue_timing_gap"],
                },
                "dimensions": ["period"],
                "metrics": ["revenue_gap_amount"],
                "comparisons": [],
                "required_evidence": [],
                "resolution_requirements": ["Resolve enterprise_name to taxpayer_id"],
                "candidate_models": ["mart_revenue_timing_gap"],
                "ambiguities": [],
                "confidence": "high",
            }
        )


class _FakePlannerAgent:
    async def plan(self, user_query, conversation_history, runtime_context, understanding_result=None):
        graph = {
            "title": "收入差异分析计划",
            "summary": "先查询差异，再审查并汇总结论。",
            "nodes": [
                {
                    "id": "query_gap",
                    "title": "查询收入差异",
                    "detail": "使用 TDA-MQL 查询华兴科技 2024Q3 差异。",
                    "status": "pending",
                    "kind": "query",
                    "tool_hints": ["mql_query"],
                    "depends_on": [],
                    "semantic_binding": {
                        "entry_model": "mart_revenue_timing_gap",
                        "metrics": ["revenue_gap_amount"],
                        "dimensions": ["period"],
                        "entity_filters": {"enterprise_name": ["华兴科技有限公司"]},
                        "query_language": "tda_mql",
                        "time_context": {"grain": "month", "range": "2024Q3"},
                    },
                }
            ],
            "edges": [],
            "active_node_ids": [],
            "source": "llm",
        }
        return SimpleNamespace(graph=graph, reasoning="优先走 MQL 主路径。", source="llm")

    async def replan(self, *args, **kwargs):
        raise AssertionError("This scenario should not trigger replan")


class _FakeExecutorAgent:
    async def execute_node(self, node, previous_results, plan_graph, user_query, runtime_context, understanding_result=None):
        return ExecutionResult(
            node_id=node["id"],
            tool_name="mql_query",
            tool_args={"model_name": "mart_revenue_timing_gap"},
            raw_result={
                "columns": ["period", "revenue_gap_amount"],
                "rows": [{"period": "2024-07", "revenue_gap_amount": -120000}],
                "row_count": 1,
            },
            thinking="使用 TDA-MQL 查询复合语义资产。",
            duration_ms=8,
        )

    def build_action_metadata(self, exec_result, plan_graph):
        return {
            "tool_name": exec_result.tool_name,
            "tool_label": "TDA-MQL 查询",
            "tool_input_summary": "执行收入差异 MQL 查询",
        }

    def build_observation_metadata(self, exec_result, plan_graph):
        return {
            "result_summary": "返回 1 行差异数据",
            "table_data": {
                "columns": ["period", "revenue_gap_amount"],
                "rows": [{"period": "2024-07", "revenue_gap_amount": -120000}],
            },
            "duration_ms": exec_result.duration_ms,
        }


class _FakeReviewerAgent:
    async def review(self, node, execution_result, user_query):
        return ReviewResult(
            verdict="approve",
            review_points=["结果字段完整", "差异值可用于最终总结"],
            issues=[],
            suggestions=[],
            summary="审查通过",
        )

    async def synthesize(self, user_query, execution_results, plan_graph=None):
        return SynthesisResult(answer="最终结论：收入差异主要来自时间性偏差。", evidence=["query_gap：1 行数据"])


async def _fake_validate_tda_mql_draft_payload(payload: dict):
    return {
        "validated_request": dict(payload),
        "validation": {
            "semantic_query": {"model_name": payload.get("model_name")},
            "unsupported_features": [],
            "relationship_graph_count": 1,
            "metric_lineage_count": 1,
            "detail_field_count": 1,
            "query_hints": {"preferred_lane": "metric"},
        },
    }


@pytest.mark.asyncio
async def test_orchestrator_emits_stage_updates_across_main_flow(monkeypatch):
    async def _fake_build_semantic_grounding(user_query: str):
        return {"candidate_models": [], "catalog_by_kind": {}}

    async def _fake_build_runtime_context(user_query: str, understanding_result=None, semantic_grounding=None):
        return {
            "query_mode": "reconciliation",
            "period_hints": {"year": 2024, "quarter": 3, "periods": ["2024-07", "2024-08", "2024-09"]},
            "enterprise_candidates": [{"enterprise_name": "华兴科技有限公司", "taxpayer_id": "91310000123456789X"}],
            "relevant_models": [
                {
                    "name": "mart_revenue_timing_gap",
                    "label": "收入时间性差异",
                    "semantic_kind": "composite_analysis",
                    "dimensions": ["period"],
                    "metrics": ["revenue_gap_amount"],
                    "recommended_tool": "mql_query",
                }
            ],
            "understanding_result": understanding_result or {},
        }

    monkeypatch.setattr(orchestrator_module, "build_semantic_grounding", _fake_build_semantic_grounding)
    monkeypatch.setattr(orchestrator_module, "build_runtime_context", _fake_build_runtime_context)
    monkeypatch.setattr(orchestrator_module, "build_runtime_status_text", lambda runtime_context: "已识别收入差异分析上下文")
    monkeypatch.setattr(orchestrator_module, "_validate_tda_mql_draft_payload", _fake_validate_tda_mql_draft_payload)

    orchestrator = MultiAgentOrchestrator(llm=None)
    orchestrator.understanding = _FakeUnderstandingAgent()
    orchestrator.planner = _FakePlannerAgent()
    orchestrator.executor = _FakeExecutorAgent()
    orchestrator.reviewer = _FakeReviewerAgent()

    events = []
    async for event in orchestrator.run("分析华兴科技 2024Q3 增值税申报收入和账面收入差异"):
        events.append(event)

    assert events[-1].type == "answer"
    assert events[-1].is_final is True

    stage_events = [event for event in events if event.type == "stage_update"]
    stage_pairs = [(event.metadata.get("stage_id"), event.metadata.get("stage_status")) for event in stage_events]

    expected_pairs = [
        ("intent_recognition", "in_progress"),
        ("intent_recognition", "completed"),
        ("semantic_binding", "in_progress"),
        ("semantic_binding", "completed"),
        ("tda_mql_draft", "in_progress"),
        ("tda_mql_draft", "completed"),
        ("feasibility_assessment", "in_progress"),
        ("feasibility_assessment", "completed"),
        ("planning", "in_progress"),
        ("planning", "completed"),
        ("metric_execution", "in_progress"),
        ("metric_execution", "completed"),
        ("detail_execution", "in_progress"),
        ("detail_execution", "completed"),
        ("evidence_verification", "in_progress"),
        ("evidence_verification", "completed"),
        ("review", "in_progress"),
        ("review", "completed"),
        ("report_generation", "in_progress"),
        ("report_generation", "completed"),
    ]
    assert stage_pairs == expected_pairs
    assert all(event.metadata.get("stage_graph", {}).get("source") == "stage_graph_v1_lite" for event in stage_events)


@pytest.mark.asyncio
async def test_orchestrator_blocks_when_tda_mql_draft_validation_fails(monkeypatch):
    async def _fake_build_semantic_grounding(user_query: str):
        return {"candidate_models": [], "catalog_by_kind": {}}

    async def _fake_build_runtime_context(user_query: str, understanding_result=None, semantic_grounding=None):
        return {
            "query_mode": "reconciliation",
            "period_hints": {"year": 2024, "quarter": 3, "periods": ["2024-07", "2024-08", "2024-09"]},
            "enterprise_candidates": [{"enterprise_name": "华兴科技有限公司", "taxpayer_id": "91310000123456789X"}],
            "relevant_models": [
                {
                    "name": "mart_revenue_timing_gap",
                    "label": "收入时间性差异",
                    "semantic_kind": "composite_analysis",
                    "dimensions": ["period"],
                    "metrics": ["revenue_gap_amount"],
                    "recommended_tool": "mql_query",
                }
            ],
            "understanding_result": understanding_result or {},
        }

    async def _fake_validate(payload: dict):
        raise SemanticDefinitionError("invalid drilldown combination")

    monkeypatch.setattr(orchestrator_module, "build_semantic_grounding", _fake_build_semantic_grounding)
    monkeypatch.setattr(orchestrator_module, "build_runtime_context", _fake_build_runtime_context)
    monkeypatch.setattr(orchestrator_module, "build_runtime_status_text", lambda runtime_context: "已识别收入差异分析上下文")
    monkeypatch.setattr(orchestrator_module, "_validate_tda_mql_draft_payload", _fake_validate)

    orchestrator = MultiAgentOrchestrator(llm=None)
    orchestrator.understanding = _FakeUnderstandingAgent()
    orchestrator.planner = _FakePlannerAgent()
    orchestrator.executor = _FakeExecutorAgent()
    orchestrator.reviewer = _FakeReviewerAgent()

    events = []
    async for event in orchestrator.run("分析华兴科技 2024Q3 增值税申报收入和账面收入差异"):
        events.append(event)

    assert events[-1].type == "error"
    assert events[-1].is_final is True
    assert "TDA-MQL draft validation failed" in events[-1].content

    stage_events = [event for event in events if event.type == "stage_update"]
    stage_pairs = [(event.metadata.get("stage_id"), event.metadata.get("stage_status")) for event in stage_events]
    assert stage_pairs == [
        ("intent_recognition", "in_progress"),
        ("intent_recognition", "completed"),
        ("semantic_binding", "in_progress"),
        ("semantic_binding", "completed"),
        ("tda_mql_draft", "in_progress"),
        ("tda_mql_draft", "blocked"),
    ]


@pytest.mark.asyncio
async def test_orchestrator_blocks_when_report_generation_fails_explicitly(monkeypatch):
    class _FailingReviewerAgent(_FakeReviewerAgent):
        async def synthesize(self, user_query, execution_results, plan_graph=None):
            return SynthesisResult(
                answer="",
                evidence=["query_gap：1 行数据"],
                success=False,
                failure_reason="报告生成失败：模型未返回最终答案。",
            )

    async def _fake_build_semantic_grounding(user_query: str):
        return {"candidate_models": [], "catalog_by_kind": {}}

    async def _fake_build_runtime_context(user_query: str, understanding_result=None, semantic_grounding=None):
        return {
            "query_mode": "reconciliation",
            "period_hints": {"year": 2024, "quarter": 3, "periods": ["2024-07", "2024-08", "2024-09"]},
            "enterprise_candidates": [{"enterprise_name": "华兴科技有限公司", "taxpayer_id": "91310000123456789X"}],
            "relevant_models": [
                {
                    "name": "mart_revenue_timing_gap",
                    "label": "收入时间性差异",
                    "semantic_kind": "composite_analysis",
                    "dimensions": ["period"],
                    "metrics": ["revenue_gap_amount"],
                    "recommended_tool": "mql_query",
                }
            ],
            "understanding_result": understanding_result or {},
        }

    monkeypatch.setattr(orchestrator_module, "build_semantic_grounding", _fake_build_semantic_grounding)
    monkeypatch.setattr(orchestrator_module, "build_runtime_context", _fake_build_runtime_context)
    monkeypatch.setattr(orchestrator_module, "build_runtime_status_text", lambda runtime_context: "已识别收入差异分析上下文")
    monkeypatch.setattr(orchestrator_module, "_validate_tda_mql_draft_payload", _fake_validate_tda_mql_draft_payload)

    orchestrator = MultiAgentOrchestrator(llm=None)
    orchestrator.understanding = _FakeUnderstandingAgent()
    orchestrator.planner = _FakePlannerAgent()
    orchestrator.executor = _FakeExecutorAgent()
    orchestrator.reviewer = _FailingReviewerAgent()

    events = []
    async for event in orchestrator.run("分析华兴科技 2024Q3 增值税申报收入和账面收入差异"):
        events.append(event)

    assert events[-1].type == "error"
    assert events[-1].is_final is True
    assert events[-1].agent == "reviewer"
    assert "报告生成失败" in events[-1].content
    assert not any(event.type == "answer" for event in events)

    stage_events = [event for event in events if event.type == "stage_update"]
    assert (stage_events[-1].metadata.get("stage_id"), stage_events[-1].metadata.get("stage_status")) == (
        "report_generation",
        "blocked",
    )


def test_build_semantic_binding_stage_payload_matches_query_terms_without_broad_defaults():
    runtime_context = {
        "period_hints": {"periods": ["2024-08"]},
        "enterprise_candidates": [{"enterprise_name": "明达制造", "taxpayer_id": "913100001"}],
        "relevant_models": [
            {
                "name": "mart_export_rebate_reconciliation",
                "label": "出口退税对账主题",
                "semantic_kind": "composite_analysis",
                "recommended_tool": "mql_query",
                "time": {"grain": "month"},
                "metric_terms": [
                    {"name": "book_net_revenue_after_discount_cny", "label": "折扣后账面可比收入"},
                    {"name": "rebate_tax_basis_after_discount_cny", "label": "折扣后税基金额"},
                    {"name": "reconciliation_gap_amount", "label": "税账对账差异金额"},
                    {"name": "discount_doc_count", "label": "折扣单据数"},
                ],
                "dimension_terms": [
                    {"name": "rebate_period", "label": "退税所属期"},
                    {"name": "contract_id", "label": "合同号"},
                    {"name": "declaration_no", "label": "报关单号"},
                    {"name": "discount_doc_no", "label": "折扣单据号"},
                    {"name": "sync_status", "label": "同步状态"},
                    {"name": "industry_name", "label": "行业名称"},
                ],
                "detail_fields": [
                    {"name": "contract_id", "label": "合同号"},
                    {"name": "declaration_no", "label": "报关单号"},
                    {"name": "discount_doc_no", "label": "折扣单据号"},
                    {"name": "sync_status", "label": "同步状态"},
                ],
            }
        ],
    }
    understanding_result = {
        "entities": {"enterprise_names": ["明达制造"]},
        "metrics": [],
        "dimensions": [],
    }

    payload = _build_semantic_binding_stage_payload(
        runtime_context,
        understanding_result,
        "分析明达制造2024年8月出口退税账面收入与税基金额差异，按退税所属期统计，并下钻到合同号和报关单号，返回合同号、报关单号、折扣单号、账面收入、税基金额、差异金额和同步状态。",
    )

    assert payload["semantic_binding"]["metrics"] == [
        "reconciliation_gap_amount",
        "rebate_tax_basis_after_discount_cny",
        "book_net_revenue_after_discount_cny",
    ]
    assert set(payload["semantic_binding"]["dimensions"]) >= {
        "rebate_period",
        "contract_id",
        "declaration_no",
        "discount_doc_no",
        "sync_status",
    }
    assert len(payload["semantic_binding"]["dimensions"]) <= 5
    assert "industry_name" not in payload["semantic_binding"]["dimensions"]
