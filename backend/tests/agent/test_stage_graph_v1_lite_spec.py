from __future__ import annotations

from types import SimpleNamespace

import pytest

import app.agent.orchestrator as orchestrator_module
from app.agent.executor_agent_v2 import ExecutionResult
from app.agent.orchestrator import MultiAgentOrchestrator
from app.agent.reviewer_agent_v2 import ReviewResult, SynthesisResult
from app.agent.stage_graph import StageGraphTracker


EXPECTED_STAGE_IDS = [
    "intent_recognition",
    "semantic_binding",
    "tda_mql_draft",
    "feasibility_assessment",
    "planning",
    "metric_execution",
    "detail_execution",
    "evidence_verification",
    "review",
    "report_generation",
]

EXPECTED_STAGE_PAIRS = []
for stage_id in EXPECTED_STAGE_IDS:
    EXPECTED_STAGE_PAIRS.append((stage_id, "in_progress"))
    EXPECTED_STAGE_PAIRS.append((stage_id, "completed"))


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
                "intent_summary": "Analyze tax reconciliation",
                "business_goal": "Validate the gap and produce a report",
                "entities": {"enterprise_names": ["Acme"]},
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
            "title": "Tax reconciliation plan",
            "summary": "Draft a TDA-MQL-first plan and verify it before execution.",
            "nodes": [
                {
                    "id": "draft_mql",
                    "title": "Draft TDA-MQL",
                    "detail": "Use TDA-MQL for the selected reconciliation asset.",
                    "status": "pending",
                    "kind": "query",
                    "tool_hints": ["mql_query"],
                    "depends_on": [],
                    "semantic_binding": {
                        "entry_model": "mart_revenue_timing_gap",
                        "metrics": ["revenue_gap_amount"],
                        "dimensions": ["period"],
                        "entity_filters": {"enterprise_name": ["Acme"]},
                        "query_language": "tda_mql",
                        "time_context": {"grain": "month", "range": "2024Q3"},
                    },
                }
            ],
            "edges": [],
            "active_node_ids": [],
            "source": "llm",
        }
        return SimpleNamespace(graph=graph, reasoning="Prefer MQL-first execution", source="llm")

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
            thinking="Execute the semantic query",
            duration_ms=8,
        )

    def build_action_metadata(self, exec_result, plan_graph):
        return {
            "tool_name": exec_result.tool_name,
            "tool_label": "TDA-MQL Query",
            "tool_input_summary": "Run reconciliation query",
        }

    def build_observation_metadata(self, exec_result, plan_graph):
        return {
            "result_summary": "Returned one row",
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
            review_points=["Result is complete", "Gap value is suitable for reporting"],
            issues=[],
            suggestions=[],
            summary="Approved",
        )

    async def synthesize(self, user_query, execution_results, plan_graph=None):
        return SynthesisResult(answer="Final report", evidence=["1 row result"])


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


def test_stage_graph_tracker_will_expose_v1_lite_stage_order():
    tracker = StageGraphTracker()

    snapshot = tracker.snapshot()
    node_ids = [node["id"] for node in snapshot["nodes"]]

    assert node_ids == EXPECTED_STAGE_IDS
    assert snapshot["source"] == "stage_graph_v1_lite"


@pytest.mark.asyncio
async def test_orchestrator_will_emit_v1_lite_stage_updates_in_order(monkeypatch):
    async def _fake_build_semantic_grounding(user_query: str):
        return {"candidate_models": [], "catalog_by_kind": {}}

    async def _fake_build_runtime_context(user_query: str, understanding_result=None, semantic_grounding=None):
        return {
            "query_mode": "reconciliation",
            "period_hints": {"year": 2024, "quarter": 3, "periods": ["2024-07", "2024-08", "2024-09"]},
            "enterprise_candidates": [{"enterprise_name": "Acme", "taxpayer_id": "999999999"}],
            "relevant_models": [
                {
                    "name": "mart_revenue_timing_gap",
                    "label": "Tax revenue timing gap",
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
    monkeypatch.setattr(orchestrator_module, "build_runtime_status_text", lambda runtime_context: "StageGraph v1-lite")
    monkeypatch.setattr(orchestrator_module, "_validate_tda_mql_draft_payload", _fake_validate_tda_mql_draft_payload)

    orchestrator = MultiAgentOrchestrator(llm=None)
    orchestrator.understanding = _FakeUnderstandingAgent()
    orchestrator.planner = _FakePlannerAgent()
    orchestrator.executor = _FakeExecutorAgent()
    orchestrator.reviewer = _FakeReviewerAgent()

    events = []
    async for event in orchestrator.run("Analyze Acme 2024Q3 tax reconciliation"):
        events.append(event)

    assert events[-1].type == "answer"
    assert events[-1].is_final is True

    stage_events = [event for event in events if event.type == "stage_update"]
    stage_pairs = [(event.metadata.get("stage_id"), event.metadata.get("stage_status")) for event in stage_events]

    assert stage_pairs == EXPECTED_STAGE_PAIRS
