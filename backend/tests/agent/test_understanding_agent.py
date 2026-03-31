from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agent.understanding_agent import UnderstandingAgent


def _response_with_content(content: str) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


class SuccessfulLLM:
    def __init__(self, content: str):
        self.content = content
        self.calls: list[dict] = []

    async def chat(self, **kwargs):
        self.calls.append(kwargs)
        return _response_with_content(self.content)


class FailingLLM:
    async def chat(self, **kwargs):
        raise RuntimeError("boom")


class InvalidJsonLLM:
    async def chat(self, **kwargs):
        return _response_with_content("not-json")


@pytest.fixture
def semantic_grounding() -> dict:
    return {
        "heuristic_query_mode": "analysis",
        "period_hints": {"periods": ["2024-07", "2024-08", "2024-09"]},
        "enterprise_candidates": [
            {"enterprise_name": "Acme Corp", "taxpayer_id": "9137"},
            {"enterprise_name": "Acme Group", "taxpayer_id": "9138"},
        ],
        "candidate_models": [
            {"name": "reconciliation_dashboard"},
            {"name": "vat_declaration"},
            {"name": "book_revenue"},
            {"name": "risk_model"},
        ],
    }


def test_normalize_result_filters_unknown_models_and_normalizes_lists(semantic_grounding):
    agent = UnderstandingAgent(llm=None)

    result = agent._normalize_result(
        {
            "query_mode": "analysis",
            "intent_summary": "   ",
            "business_goal": "Compare declared and booked revenue",
            "entities": {
                "enterprise_names": ["Acme Corp", "Acme Corp", ""],
                "taxpayer_ids": ["9137", "9137"],
                "tax_types": ["VAT"],
                "periods": ["2024-07", "2024-07"],
            },
            "dimensions": ["period", "period", "enterprise_name"],
            "metrics": ["vat_declared_revenue", "vat_declared_revenue"],
            "comparisons": [
                {"left": "declared", "right": "booked", "operator": ""},
                "ignored",
                {"left": "", "right": "", "operator": "diff"},
            ],
            "required_evidence": ["declared", "booked", "declared"],
            "candidate_models": ["unknown_model", "vat_declaration", "vat_declaration"],
            "ambiguities": ["need exact tax type", "need exact tax type"],
            "confidence": "HIGH",
        },
        semantic_grounding,
    )

    assert result.query_mode == "analysis"
    assert result.intent_summary == "Compare declared and booked revenue"
    assert result.business_goal == "Compare declared and booked revenue"
    assert result.entities == {
        "enterprise_names": ["Acme Corp"],
        "taxpayer_ids": ["9137"],
        "tax_types": ["VAT"],
        "periods": ["2024-07"],
    }
    assert result.dimensions == ["period", "enterprise_name"]
    assert result.metrics == ["vat_declared_revenue"]
    assert result.comparisons == [
        {"left": "declared", "right": "booked", "operator": "compare"}
    ]
    assert result.required_evidence == ["declared", "booked"]
    assert result.candidate_models == ["vat_declaration"]
    assert result.ambiguities == ["need exact tax type"]
    assert result.confidence == "high"


def test_normalize_result_falls_back_to_top_grounding_models_when_none_match(semantic_grounding):
    agent = UnderstandingAgent(llm=None)

    result = agent._normalize_result(
        {
            "business_goal": "Check revenue mismatch",
            "candidate_models": ["missing_model"],
        },
        semantic_grounding,
    )

    assert result.candidate_models == [
        "reconciliation_dashboard",
        "vat_declaration",
        "book_revenue",
    ]


@pytest.mark.asyncio
async def test_understand_uses_llm_json_response(semantic_grounding):
    llm = SuccessfulLLM(
        """
        ```json
        {
          "query_mode": "reconciliation",
          "intent_summary": "Compare declared and booked revenue by month",
          "business_goal": "Find the monthly revenue gap",
          "entities": {"enterprise_names": ["Acme Corp"], "periods": ["2024-07"]},
          "dimensions": ["period"],
          "metrics": ["vat_declared_revenue"],
          "candidate_models": ["reconciliation_dashboard"],
          "confidence": "medium"
        }
        ```
        """
    )
    agent = UnderstandingAgent(llm=llm)

    result = await agent.understand("Compare Acme revenue", [], semantic_grounding)

    assert result.to_dict()["query_mode"] == "reconciliation"
    assert result.intent_summary == "Compare declared and booked revenue by month"
    assert result.entities["enterprise_names"] == ["Acme Corp"]
    assert result.candidate_models == ["reconciliation_dashboard"]
    assert llm.calls[0]["response_format"] == {"type": "json_object"}


@pytest.mark.asyncio
async def test_understand_falls_back_when_llm_raises(semantic_grounding):
    agent = UnderstandingAgent(llm=FailingLLM())

    result = await agent.understand(
        "Why is Acme revenue different in Q3 2024?",
        [],
        semantic_grounding,
    )

    assert result.query_mode == "analysis"
    assert result.confidence == "low"
    assert result.entities["enterprise_names"] == ["Acme Corp", "Acme Group"]
    assert result.entities["taxpayer_ids"] == ["9137", "9138"]
    assert result.entities["periods"] == ["2024-07", "2024-08", "2024-09"]
    assert result.candidate_models == [
        "reconciliation_dashboard",
        "vat_declaration",
        "book_revenue",
    ]
    assert result.used_fallback is True
    assert result.failure_type == "llm_call_failed"
    assert "意图识别调用失败" in result.failure_message
    assert "Why is Acme revenue different in Q3 2024" in result.intent_summary


@pytest.mark.asyncio
async def test_understand_falls_back_when_llm_returns_invalid_json(semantic_grounding):
    agent = UnderstandingAgent(llm=InvalidJsonLLM())

    result = await agent.understand(
        "Compare Acme revenue",
        [],
        semantic_grounding,
    )

    assert result.used_fallback is True
    assert result.failure_type == "response_parse_failed"
    assert "不可解析" in result.failure_message
