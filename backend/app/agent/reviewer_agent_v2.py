"""Reviewer Agent for node review and final synthesis."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from app.agent.planner import parse_plan_json
from app.agent.prompts.reviewer_prompt_v2 import (
    REVIEWER_NODE_TEMPLATE,
    REVIEWER_SYSTEM_PROMPT,
    SYNTHESIZE_SYSTEM_PROMPT,
    SYNTHESIZE_TEMPLATE,
)


class ReviewResult:
    """Reviewer verdict for a single execution step."""

    __slots__ = ("verdict", "review_points", "issues", "suggestions", "summary")

    def __init__(
        self,
        verdict: str = "approve",
        review_points: list[str] | None = None,
        issues: list[str] | None = None,
        suggestions: list[str] | None = None,
        summary: str = "",
    ):
        self.verdict = verdict
        self.review_points = review_points or []
        self.issues = issues or []
        self.suggestions = suggestions or []
        self.summary = summary

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "review_points": self.review_points,
            "issues": self.issues,
            "suggestions": self.suggestions,
            "summary": self.summary,
        }


class SynthesisResult:
    """Final report from the reviewer."""

    __slots__ = ("answer", "evidence", "success", "failure_reason")

    def __init__(
        self,
        answer: str,
        evidence: list[str] | None = None,
        *,
        success: bool = True,
        failure_reason: str = "",
    ):
        self.answer = answer
        self.evidence = evidence or []
        self.success = success
        self.failure_reason = failure_reason


class ReviewerAgent:
    """Reviews execution quality and synthesizes final answers."""

    QUARTER_TO_MONTHS = {
        1: {"01", "02", "03"},
        2: {"04", "05", "06"},
        3: {"07", "08", "09"},
        4: {"10", "11", "12"},
    }

    def __init__(self, llm: Any):
        self.llm = llm

    async def review(
        self,
        node: dict[str, Any],
        execution_result: Any,
        user_query: str,
    ) -> ReviewResult:
        """Review a single node's execution result."""
        result_str = self._format_result(execution_result)
        user_content = REVIEWER_NODE_TEMPLATE.format(
            user_query=user_query,
            node_title=node.get("title", ""),
            node_kind=node.get("kind", ""),
            execution_result=result_str,
        )

        try:
            response = await asyncio.wait_for(
                self.llm.chat(
                    messages=[
                        {"role": "system", "content": REVIEWER_SYSTEM_PROMPT},
                        {"role": "user", "content": user_content},
                    ],
                    trace={
                        "agent": "reviewer",
                        "operation": "review_node",
                        "node_id": node.get("id", ""),
                        "node_title": node.get("title", ""),
                    },
                    stream=False,
                    temperature=0.0,
                    max_tokens=500,
                    response_format={"type": "json_object"},
                ),
                timeout=15,
            )
            raw = response.choices[0].message.content or ""
            parsed = parse_plan_json(raw)
            if not parsed:
                return ReviewResult(
                    verdict="error",
                    issues=["review_parse_failed"],
                    suggestions=["请重试审查阶段，并检查审查提示词与模型输出格式。"],
                    summary="审查输出不可解析，已停止默认放行。",
                )

            review = ReviewResult(
                verdict=str(parsed.get("verdict", "approve")),
                review_points=parsed.get("review_points", []),
                issues=parsed.get("issues", []),
                suggestions=parsed.get("suggestions", []),
                summary=str(parsed.get("summary", "")),
            )
            return self._override_review_if_needed(review, execution_result, user_query)
        except Exception as exc:
            return ReviewResult(
                verdict="error",
                issues=[f"review_exception:{type(exc).__name__}"],
                suggestions=["请重试本轮审查，必要时检查模型连通性与超时设置。"],
                summary="审查阶段失败，已停止默认放行。",
            )

    async def synthesize(
        self,
        user_query: str,
        execution_results: dict[str, Any],
        plan_graph: dict[str, Any] | None = None,
    ) -> SynthesisResult:
        """Generate the final answer from all execution results."""
        execution_summary, evidence = self._build_execution_summary(execution_results, plan_graph)
        user_content = SYNTHESIZE_TEMPLATE.format(
            user_query=user_query,
            execution_summary=execution_summary,
        )

        try:
            response = await asyncio.wait_for(
                self.llm.chat(
                    messages=[
                        {"role": "system", "content": SYNTHESIZE_SYSTEM_PROMPT},
                        {"role": "user", "content": user_content},
                    ],
                    trace={"agent": "reviewer", "operation": "synthesize_answer"},
                    stream=False,
                    temperature=0.0,
                    max_tokens=1100,
                ),
                timeout=60,
            )
            answer = (response.choices[0].message.content or "").strip()
            if not answer:
                return SynthesisResult(
                    answer="",
                    evidence=evidence,
                    success=False,
                    failure_reason="报告生成返回空内容，未输出最终答案。",
                )
            return SynthesisResult(answer=answer, evidence=evidence)
        except Exception:
            return SynthesisResult(
                answer="",
                evidence=evidence,
                success=False,
                failure_reason="报告生成失败，未输出最终答案。",
            )

    def _build_execution_summary(
        self,
        execution_results: dict[str, Any],
        plan_graph: dict[str, Any] | None,
    ) -> tuple[str, list[str]]:
        summary_lines: list[str] = []
        evidence: list[str] = []

        for node_id, result in execution_results.items():
            node_title = self._resolve_node_title(node_id, plan_graph)

            if hasattr(result, "error") and result.error:
                summary_lines.append(f"### {node_title or node_id}\n执行失败：{result.error}")
                continue

            if hasattr(result, "raw_result") and result.raw_result is not None:
                raw = result.raw_result
                tool_name = getattr(result, "tool_name", "")
                summary_lines.append(
                    f"### {node_title or node_id}\n工具：{tool_name}\n{self._summarize_raw_result(raw)}"
                )
                if isinstance(raw, dict) and raw.get("row_count") is not None:
                    evidence.append(f"{node_title or node_id}：{raw['row_count']} 行数据")
                continue

            thinking = getattr(result, "thinking", "")
            if thinking:
                summary_lines.append(f"### {node_title or node_id}\n{thinking}")

        return "\n\n".join(summary_lines) or "无可用执行结果。", evidence

    def _resolve_node_title(self, node_id: str, plan_graph: dict[str, Any] | None) -> str:
        if not plan_graph:
            return ""
        for node in plan_graph.get("nodes", []):
            if node.get("id") == node_id:
                return str(node.get("title", ""))
        return ""

    def _override_review_if_needed(
        self,
        review: ReviewResult,
        execution_result: Any,
        user_query: str,
    ) -> ReviewResult:
        if review.verdict != "reject":
            return review
        if not self._covers_requested_quarter(execution_result, user_query):
            return review
        return ReviewResult(
            verdict="approve",
            review_points=self._merge_unique(
                review.review_points,
                ["结果已覆盖用户指定季度的完整月份，可直接用于季度汇总分析。"],
            ),
            issues=[],
            suggestions=self._merge_unique(
                review.suggestions,
                ["无需重规划，直接在最终回答阶段汇总季度累计差异与归因。"],
            ),
            summary="结果已覆盖目标季度全部月份，可直接进入最终汇总，无需重规划。",
        )

    def _format_result(self, execution_result: Any) -> str:
        """Format an execution result for review prompts."""
        if hasattr(execution_result, "raw_result"):
            raw = execution_result.raw_result
            error = getattr(execution_result, "error", "")
            if error:
                return f"错误：{error}"
            if raw is None:
                thinking = getattr(execution_result, "thinking", "")
                return thinking or "无工具调用结果。"
            return self._summarize_raw_result(raw)

        if isinstance(execution_result, dict):
            return self._summarize_raw_result(execution_result)

        return self._trim_text(str(execution_result), 2000)

    def _summarize_raw_result(self, raw: Any) -> str:
        if not isinstance(raw, dict):
            return self._trim_text(json.dumps(raw, ensure_ascii=False, default=str), 1800)

        parts: list[str] = []
        row_count = raw.get("row_count")
        if row_count is not None:
            parts.append(f"row_count={row_count}")

        columns = raw.get("columns")
        if isinstance(columns, list) and columns:
            parts.append(
                "columns=" + ", ".join(self._trim_text(str(column), 40) for column in columns[:10])
            )

        rows = raw.get("rows")
        if isinstance(rows, list) and rows:
            parts.append(
                "sample_rows=" + json.dumps(rows[:3], ensure_ascii=False, default=str)
            )

        sql = raw.get("sql")
        if sql:
            parts.append("sql=" + self._trim_text(str(sql).replace("\n", " "), 500))

        if not parts:
            parts.append(self._trim_text(json.dumps(raw, ensure_ascii=False, default=str), 1800))

        return "\n".join(parts)

    def _trim_text(self, text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        return text[: limit - 1] + "…"

    def _covers_requested_quarter(self, execution_result: Any, user_query: str) -> bool:
        raw = getattr(execution_result, "raw_result", None)
        if not isinstance(raw, dict):
            return False

        expected_periods = self._extract_expected_periods(user_query)
        if len(expected_periods) < 3:
            return False

        rows = raw.get("rows")
        if not isinstance(rows, list) or not rows:
            return False

        actual_periods = {
            str(row.get("period") or row.get("tax_period") or "").strip()
            for row in rows
            if isinstance(row, dict)
        }
        if not expected_periods.issubset(actual_periods):
            return False

        metric_fields = {"vat_vs_acct_diff", "cit_vs_acct_diff", "vat_declared_revenue", "acct_book_revenue"}
        return any(
            isinstance(row, dict) and any(field in row for field in metric_fields)
            for row in rows
        )

    def _extract_expected_periods(self, user_query: str) -> set[str]:
        text = user_query or ""
        year_match = re.search(r"(20\d{2})", text)
        quarter_match = re.search(r"Q\s*([1-4])", text, flags=re.IGNORECASE)
        if not quarter_match:
            quarter_match = re.search(r"([1234一二三四])季度", text)
        if not year_match or not quarter_match:
            return set()

        year = year_match.group(1)
        token = quarter_match.group(1)
        quarter = {"一": 1, "二": 2, "三": 3, "四": 4}.get(token, int(token))
        return {f"{year}-{month}" for month in self.QUARTER_TO_MONTHS.get(quarter, set())}

    def _merge_unique(self, *groups: list[Any]) -> list[str]:
        merged: list[str] = []
        for group in groups:
            for item in group or []:
                text = str(item or "").strip()
                if text and text not in merged:
                    merged.append(text)
        return merged
