from __future__ import annotations

import pytest

from app.agent.executor_agent_v2 import ExecutorAgent


@pytest.mark.asyncio
async def test_execute_semantic_first_uses_mql_query_when_binding_requests_it(monkeypatch):
    captured: dict = {}

    async def fake_mql_query(**kwargs):
        captured.update(kwargs)
        return {
            "columns": ["period", "revenue_gap_amount"],
            "rows": [],
            "row_count": 0,
        }

    monkeypatch.setitem(
        __import__("app.agent.executor_agent_v2", fromlist=["TOOL_FUNCTIONS"]).TOOL_FUNCTIONS,
        "mql_query",
        fake_mql_query,
    )

    agent = ExecutorAgent(llm=None)
    node = {
        "id": "n1",
        "kind": "analysis",
        "tool_hints": ["mql_query"],
        "semantic_binding": {
            "entry_model": "mart_revenue_timing_gap",
            "query_language": "tda_mql",
            "metrics": ["revenue_gap_amount"],
            "dimensions": ["period"],
            "entity_filters": {"enterprise_name": ["华兴科技有限公司"]},
            "grain": "month",
        },
    }
    runtime_context = {
        "query_mode": "reconciliation",
        "period_hints": {
            "year": 2024,
            "quarter": 3,
            "periods": ["2024-07", "2024-08", "2024-09"],
        },
        "relevant_models": [
            {
                "name": "mart_revenue_timing_gap",
                "metrics": ["revenue_gap_amount"],
                "dimensions": ["period", "enterprise_name"],
                "semantic_kind": "composite_analysis",
            }
        ],
    }

    result = await agent._execute_semantic_first(node=node, runtime_context=runtime_context)

    assert result is not None
    assert result.tool_name == "mql_query"
    assert result.error == ""
    assert captured["model_name"] == "mart_revenue_timing_gap"
    assert captured["select"] == [{"metric": "revenue_gap_amount"}]
    assert captured["group_by"] == ["period"]
    assert captured["time_context"] == {"grain": "month", "range": "2024Q3"}


def test_select_tool_definitions_locks_to_mql_query_for_explicit_mql_binding():
    agent = ExecutorAgent(llm=None)
    node = {
        "kind": "analysis",
        "tool_hints": ["mql_query", "sql_executor"],
        "semantic_binding": {
            "entry_model": "mart_revenue_timing_gap",
            "query_language": "tda_mql",
            "metrics": ["revenue_gap_amount"],
        },
    }

    definitions = agent._select_tool_definitions(node, {"query_mode": "reconciliation"})
    tool_names = [item["function"]["name"] for item in definitions]

    assert tool_names == ["mql_query"]


def test_tda_mql_binding_disables_hidden_fallback():
    agent = ExecutorAgent(llm=None)

    assert agent._binding_allows_fallback({"query_language": "tda_mql", "fallback_policy": "atomic_then_sql"}) is False


@pytest.mark.asyncio
async def test_execute_semantic_first_preserves_explicit_time_role(monkeypatch):
    captured: dict = {}

    async def fake_mql_query(**kwargs):
        captured.update(kwargs)
        return {
            "columns": ["contract_id", "reconciliation_gap_amount"],
            "rows": [],
            "row_count": 0,
        }

    monkeypatch.setitem(
        __import__("app.agent.executor_agent_v2", fromlist=["TOOL_FUNCTIONS"]).TOOL_FUNCTIONS,
        "mql_query",
        fake_mql_query,
    )

    agent = ExecutorAgent(llm=None)
    node = {
        "id": "n2",
        "kind": "analysis",
        "tool_hints": ["mql_query"],
        "semantic_binding": {
            "entry_model": "mart_export_rebate_reconciliation",
            "query_language": "tda_mql",
            "metrics": ["reconciliation_gap_amount"],
            "dimensions": ["contract_id"],
            "time_context": {"grain": "month", "range": "2024-08", "role": "book_period"},
        },
    }

    result = await agent._execute_semantic_first(node=node, runtime_context={"query_mode": "analysis"})

    assert result is not None
    assert result.error == ""
    assert captured["time_context"] == {"grain": "month", "range": "2024-08", "role": "book_period"}
