"""Planner Agent with runtime grounding and plan validation."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from app.agent.plan_presentation import build_fallback_plan_graph, normalize_plan_graph
from app.agent.planner import append_planner_debug_log, parse_plan_json, trim_conversation_history
from app.agent.prompts.planner_prompt_v3 import PLANNER_SYSTEM_PROMPT, REPLAN_SYSTEM_PROMPT
from app.agent.runtime_context import build_runtime_context, validate_plan_graph


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
        runtime_context: dict[str, Any] | None = None,
        understanding_result: dict[str, Any] | None = None,
    ) -> PlanResult:
        """Generate the initial execution plan."""
        runtime_context = runtime_context or await build_runtime_context(user_query)
        payload = {
            "user_query": user_query,
            "conversation_history": trim_conversation_history(conversation_history),
            "runtime_context": runtime_context,
            "understanding_result": understanding_result or runtime_context.get("understanding_result") or {},
        }

        raw_content = ""
        try:
            reasoning, normalized, raw_content = await self._generate_valid_plan(
                user_query=user_query,
                runtime_context=runtime_context,
                system_prompt=PLANNER_SYSTEM_PROMPT,
                request_payload=payload,
                max_tokens=1200,
                timeout=45,
                change_reason_required=False,
            )
            return PlanResult(graph=normalized, reasoning=reasoning, source="llm")
        except Exception as exc:
            append_planner_debug_log(
                user_query=user_query,
                payload={"mode": "initial", "runtime_context": runtime_context},
                raw_content=raw_content,
                error=f"{type(exc).__name__}: {exc}",
            )
            fallback = build_fallback_plan_graph(user_query)
            return PlanResult(graph=fallback, reasoning="规划失败，使用保底路径。", source="fallback")

    async def replan(
        self,
        user_query: str,
        current_plan: dict[str, Any],
        review_feedback: dict[str, Any],
        execution_context: dict[str, Any] | None = None,
        runtime_context: dict[str, Any] | None = None,
        understanding_result: dict[str, Any] | None = None,
    ) -> PlanResult:
        """Revise the plan based on Reviewer feedback."""
        runtime_context = runtime_context or await build_runtime_context(user_query)
        payload = {
            "user_query": user_query,
            "current_plan": current_plan,
            "review_feedback": review_feedback,
            "execution_context": execution_context or {},
            "runtime_context": runtime_context,
            "understanding_result": understanding_result or runtime_context.get("understanding_result") or {},
        }

        raw_content = ""
        try:
            reasoning, normalized, raw_content = await self._generate_valid_plan(
                user_query=user_query,
                runtime_context=runtime_context,
                system_prompt=REPLAN_SYSTEM_PROMPT,
                request_payload=payload,
                max_tokens=1000,
                timeout=35,
                change_reason_required=True,
            )
            return PlanResult(graph=normalized, reasoning=reasoning, source="llm")
        except Exception as exc:
            append_planner_debug_log(
                user_query=user_query,
                payload={"mode": "replan", "runtime_context": runtime_context},
                raw_content=raw_content,
                error=f"{type(exc).__name__}: {exc}",
            )
            current_plan["change_reason"] = f"重规划失败（{exc}），沿用原计划。"
            return PlanResult(graph=current_plan, reasoning="重规划失败。", source="fallback")

    async def _generate_valid_plan(
        self,
        user_query: str,
        runtime_context: dict[str, Any],
        system_prompt: str,
        request_payload: dict[str, Any],
        max_tokens: int,
        timeout: int,
        change_reason_required: bool,
    ) -> tuple[str, dict[str, Any], str]:
        last_error: Exception | None = None
        validation_feedback: list[str] = []
        raw_content = ""

        for _attempt in range(2):
            payload = dict(request_payload)
            if validation_feedback:
                payload["validation_feedback"] = validation_feedback

            response = await asyncio.wait_for(
                self.llm.chat(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                    ],
                    stream=False,
                    temperature=0.0,
                    max_tokens=max_tokens,
                    response_format={"type": "json_object"},
                ),
                timeout=timeout,
            )
            raw_content = response.choices[0].message.content or ""
            parsed = parse_plan_json(raw_content)
            if not parsed:
                last_error = ValueError("planner returned empty JSON")
                validation_feedback = ["上一版输出不是有效 JSON，请只返回完整 JSON 对象。"]
                continue

            reasoning = str(parsed.get("reasoning", ""))
            plan_graph_raw = parsed.get("plan_graph", parsed)
            if "nodes" not in plan_graph_raw and "nodes" in parsed:
                plan_graph_raw = parsed

            normalized = normalize_plan_graph(plan_graph_raw, user_query=user_query)
            normalized["source"] = "llm"
            if change_reason_required and not normalized.get("change_reason"):
                normalized["change_reason"] = reasoning[:120]

            issues = validate_plan_graph(normalized, runtime_context)
            if not issues:
                return reasoning, normalized, raw_content

            validation_feedback = issues
            last_error = ValueError("; ".join(issues))

        raise last_error or ValueError("planner failed to generate a valid plan")
