from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agent.reviewer_agent_v2 import ReviewerAgent


def _llm_response(content: str):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


class _InvalidJsonReviewerLlm:
    async def chat(self, *args, **kwargs):
        return _llm_response("not-json")


class _FailingSynthesisLlm:
    async def chat(self, *args, **kwargs):
        raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_review_rejects_when_reviewer_output_is_not_valid_json():
    agent = ReviewerAgent(_InvalidJsonReviewerLlm())

    result = await agent.review(
        node={"id": "query_gap", "title": "Query Gap", "kind": "query"},
        execution_result={"row_count": 1},
        user_query="分析 2024Q3 收入差异",
    )

    assert result.verdict == "error"
    assert result.issues[0] == "review_parse_failed"
    assert "审查输出不可解析" in result.summary


@pytest.mark.asyncio
async def test_synthesize_returns_explicit_failure_instead_of_fallback_answer():
    agent = ReviewerAgent(_FailingSynthesisLlm())

    result = await agent.synthesize(
        user_query="分析 2024Q3 收入差异",
        execution_results={"query_gap": {"row_count": 1}},
        plan_graph=None,
    )

    assert result.success is False
    assert result.answer == ""
    assert "报告生成失败" in result.failure_reason
