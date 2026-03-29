"""Planner Agent — intent analysis, DAG planning, and re-planning."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from app.agent.plan_presentation import normalize_plan_graph, build_fallback_plan_graph
from app.agent.planner import parse_plan_json, trim_conversation_history, append_planner_debug_log
from app.agent.prompts.planner_prompt_clean import PLANNER_SYSTEM_PROMPT, REPLAN_SYSTEM_PROMPT


class PlanResult:
    """Container for planner output."""

    __slots__ = ("graph", "reasoning", "source")

    def __init__(self, graph: dict[str, Any], reasoning: str, source: str):
        self.graph = graph
        self.reasoning = reasoning
        self.source = source


class PlannerAgent:
    """Generates and revises DAG execution plans."""

    def __init__(self, llm: Any):
        self.llm = llm

    async def plan(
        self,
        user_query: str,
        conversation_history: list[dict[str, Any]],
    ) -> PlanResult:
        """Generate the initial execution plan."""
        payload = json.dumps({
            "user_query": user_query,
            "conversation_history": trim_conversation_history(conversation_history),
        }, ensure_ascii=False)

        raw_content = ""
        try:
            response = await asyncio.wait_for(
                self.llm.chat(
                    messages=[
                        {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
                        {"role": "user", "content": payload},
                    ],
                    stream=False,
                    temperature=0.0,
                    max_tokens=1200,
                    response_format={"type": "json_object"},
                ),
                timeout=45,
            )
            raw_content = response.choices[0].message.content or ""
            parsed = parse_plan_json(raw_content)
            if not parsed:
                raise ValueError("planner returned empty JSON")

            reasoning = str(parsed.get("reasoning", ""))
            plan_graph_raw = parsed.get("plan_graph", parsed)
            # If the model wrapped graph inside plan_graph key, use that;
            # otherwise the whole parsed object is the graph itself.
            if "nodes" not in plan_graph_raw and "nodes" in parsed:
                plan_graph_raw = parsed

            normalized = normalize_plan_graph(plan_graph_raw, user_query=user_query)
            normalized["source"] = "llm"
            return PlanResult(graph=normalized, reasoning=reasoning, source="llm")

        except Exception as exc:
            append_planner_debug_log(
                user_query=user_query, payload={"mode": "initial"},
                raw_content=raw_content, error=f"{type(exc).__name__}: {exc}",
            )
            fallback = build_fallback_plan_graph(user_query)
            return PlanResult(graph=fallback, reasoning="规划失败，使用保底路径。", source="fallback")

    async def replan(
        self,
        user_query: str,
        current_plan: dict[str, Any],
        review_feedback: dict[str, Any],
        execution_context: dict[str, Any] | None = None,
    ) -> PlanResult:
        """Revise the plan based on Reviewer feedback."""
        payload = json.dumps({
            "user_query": user_query,
            "current_plan": current_plan,
            "review_feedback": review_feedback,
            "execution_context": execution_context or {},
        }, ensure_ascii=False)

        raw_content = ""
        try:
            response = await asyncio.wait_for(
                self.llm.chat(
                    messages=[
                        {"role": "system", "content": REPLAN_SYSTEM_PROMPT},
                        {"role": "user", "content": payload},
                    ],
                    stream=False,
                    temperature=0.0,
                    max_tokens=1000,
                    response_format={"type": "json_object"},
                ),
                timeout=35,
            )
            raw_content = response.choices[0].message.content or ""
            parsed = parse_plan_json(raw_content)
            if not parsed:
                raise ValueError("replan returned empty JSON")

            reasoning = str(parsed.get("reasoning", ""))
            plan_graph_raw = parsed.get("plan_graph", parsed)
            if "nodes" not in plan_graph_raw and "nodes" in parsed:
                plan_graph_raw = parsed

            normalized = normalize_plan_graph(plan_graph_raw, user_query=user_query)
            normalized["source"] = "llm"
            normalized["change_reason"] = normalized.get("change_reason") or reasoning[:120]
            return PlanResult(graph=normalized, reasoning=reasoning, source="llm")

        except Exception as exc:
            append_planner_debug_log(
                user_query=user_query, payload={"mode": "replan"},
                raw_content=raw_content, error=f"{type(exc).__name__}: {exc}",
            )
            # On replan failure, return the original plan unchanged
            current_plan["change_reason"] = f"重规划失败({exc})，沿用原计划。"
            return PlanResult(graph=current_plan, reasoning="重规划失败。", source="fallback")
