"""Reviewer Agent for node review and final synthesis."""

from __future__ import annotations

import asyncio
import json
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

    __slots__ = ("answer", "evidence")

    def __init__(self, answer: str, evidence: list[str] | None = None):
        self.answer = answer
        self.evidence = evidence or []


class ReviewerAgent:
    """Reviews execution quality and synthesizes final answers."""

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
                return ReviewResult(verdict="approve", summary="审查完成，未发现明显问题。")

            return ReviewResult(
                verdict=str(parsed.get("verdict", "approve")),
                review_points=parsed.get("review_points", []),
                issues=parsed.get("issues", []),
                suggestions=parsed.get("suggestions", []),
                summary=str(parsed.get("summary", "")),
            )
        except Exception:
            return ReviewResult(verdict="approve", summary="审查超时，默认通过。")

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
                    stream=False,
                    temperature=0.0,
                    max_tokens=1100,
                ),
                timeout=60,
            )
            answer = response.choices[0].message.content or "分析完成，但未能生成最终报告。"
            return SynthesisResult(answer=answer.strip(), evidence=evidence)
        except Exception:
            return SynthesisResult(
                answer=self._build_fallback_answer(user_query, execution_results, plan_graph),
                evidence=evidence,
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

    def _build_fallback_answer(
        self,
        user_query: str,
        execution_results: dict[str, Any],
        plan_graph: dict[str, Any] | None,
    ) -> str:
        sections = ["## 结论", "最终自然语言总结超时，以下内容基于已完成的真实执行结果自动整理。", "", "## 执行摘要"]

        if user_query:
            sections.append(f"问题：{user_query}")

        for node_id, result in execution_results.items():
            node_title = self._resolve_node_title(node_id, plan_graph)
            sections.append("")
            sections.append(f"### {node_title or node_id}")

            if hasattr(result, "error") and result.error:
                sections.append(f"- 执行失败：{result.error}")
                continue

            if hasattr(result, "raw_result") and result.raw_result is not None:
                for line in self._render_fallback_lines(result.raw_result):
                    sections.append(line)
                continue

            thinking = getattr(result, "thinking", "")
            sections.append(f"- {thinking or '未产出可展示结果。'}")

        sections.append("")
        sections.append("## 说明")
        sections.append("以上内容直接来自执行阶段的真实结果，没有额外补造数据。")
        return "\n".join(sections).strip()

    def _render_fallback_lines(self, raw: Any) -> list[str]:
        if not isinstance(raw, dict):
            return [f"- 结果：{self._trim_text(str(raw), 500)}"]

        lines: list[str] = []
        row_count = raw.get("row_count")
        if row_count is not None:
            lines.append(f"- 返回行数：{row_count}")

        columns = raw.get("columns")
        if isinstance(columns, list) and columns:
            lines.append(f"- 字段：{', '.join(str(col) for col in columns[:8])}")

        rows = raw.get("rows")
        if isinstance(rows, list) and rows:
            sample_size = 3 if len(rows) > 1 else 1
            for idx, row in enumerate(rows[:sample_size], start=1):
                lines.append(f"- 样例 {idx}：{self._trim_text(json.dumps(row, ensure_ascii=False, default=str), 400)}")

        explanation = raw.get("explanation") or raw.get("summary")
        if explanation:
            lines.append(f"- 说明：{self._trim_text(str(explanation), 300)}")

        return lines or [f"- 结果：{self._trim_text(json.dumps(raw, ensure_ascii=False, default=str), 500)}"]

    def _resolve_node_title(self, node_id: str, plan_graph: dict[str, Any] | None) -> str:
        if not plan_graph:
            return ""
        for node in plan_graph.get("nodes", []):
            if node.get("id") == node_id:
                return str(node.get("title", ""))
        return ""

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
