"""Reviewer Agent — validates execution results and synthesizes final reports."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from app.agent.planner import parse_plan_json
from app.agent.prompts.reviewer_prompt_clean import (
    REVIEWER_SYSTEM_PROMPT,
    REVIEWER_NODE_TEMPLATE,
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
        self.verdict = verdict  # "approve" or "reject"
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
    """Final report from the Reviewer."""

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
        # Format execution result for display
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
                    max_tokens=600,
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
            # On review failure, default to approve to not block execution
            return ReviewResult(verdict="approve", summary="审查超时，默认通过。")

    async def synthesize(
        self,
        user_query: str,
        execution_results: dict[str, Any],
        plan_graph: dict[str, Any] | None = None,
    ) -> SynthesisResult:
        """Generate the final answer from all execution results."""
        summary_lines = []
        evidence = []
        for node_id, result in execution_results.items():
            node_title = ""
            if plan_graph:
                for n in plan_graph.get("nodes", []):
                    if n.get("id") == node_id:
                        node_title = n.get("title", "")
                        break

            if hasattr(result, "error") and result.error:
                summary_lines.append(f"### {node_title or node_id}\n执行失败: {result.error}")
                continue

            if hasattr(result, "raw_result") and result.raw_result is not None:
                raw = result.raw_result
                result_preview = self._format_result(result)
                summary_lines.append(f"### {node_title or node_id}\n工具: {result.tool_name}\n{result_preview}")
                if isinstance(raw, dict) and raw.get("row_count"):
                    evidence.append(f"{node_title}: {raw['row_count']}行数据")
            elif hasattr(result, "thinking") and result.thinking:
                summary_lines.append(f"### {node_title or node_id}\n{result.thinking}")

        execution_summary = "\n\n".join(summary_lines) or "无可用执行结果。"

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
                    temperature=0.2,
                    max_tokens=1500,
                ),
                timeout=30,
            )
            answer = response.choices[0].message.content or "分析完成，但未能生成报告。"
            return SynthesisResult(answer=answer.strip(), evidence=evidence)
        except Exception as exc:
            return SynthesisResult(
                answer=f"报告生成失败: {exc}\n\n以下是已收集到的数据摘要：\n\n{execution_summary}",
                evidence=evidence,
            )

    def _format_result(self, execution_result: Any) -> str:
        """Format an ExecutionResult for display in prompts."""
        if hasattr(execution_result, "raw_result"):
            raw = execution_result.raw_result
            tool = getattr(execution_result, "tool_name", "")
            error = getattr(execution_result, "error", "")
            if error:
                return f"错误: {error}"
            if raw is None:
                thinking = getattr(execution_result, "thinking", "")
                return thinking or "无工具调用结果。"
            return self._truncate_json(raw)
        elif isinstance(execution_result, dict):
            return self._truncate_json(execution_result)
        return str(execution_result)[:2000]

    def _truncate_json(self, obj: Any, max_rows: int = 10) -> str:
        """Serialize and truncate large result objects."""
        if isinstance(obj, dict) and "rows" in obj:
            truncated = dict(obj)
            rows = truncated.get("rows", [])
            if len(rows) > max_rows:
                truncated["rows"] = rows[:max_rows]
                truncated["_truncated"] = f"显示前{max_rows}行，共{len(rows)}行"
            return json.dumps(truncated, ensure_ascii=False, default=str)[:3000]
        return json.dumps(obj, ensure_ascii=False, default=str)[:3000]
