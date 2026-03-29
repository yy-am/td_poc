"""Multi-Agent Orchestrator — coordinates Planner, Executor, and Reviewer agents."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, AsyncGenerator

from app.agent.planner_agent_v2 import PlannerAgent
from app.agent.executor_agent_v2 import ExecutorAgent, ExecutionResult
from app.agent.reviewer_agent_v2 import ReviewerAgent
from app.agent.plan_presentation import (
    build_plan_metadata,
    plan_graph_signature,
)
from app.agent.runtime_context import build_runtime_context, build_runtime_status_text


MAX_REPLAN_ATTEMPTS = 2
MAX_TOTAL_STEPS = 20


@dataclass
class AgentEvent:
    """A single event emitted during multi-agent execution."""

    type: str  # agent_start, plan, plan_update, thinking, action, observation, review, replan_trigger, answer, error, status
    agent: str  # planner, executor, reviewer, orchestrator
    content: str
    step_number: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    is_final: bool = False
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "agent": self.agent,
            "step_number": self.step_number,
            "content": self.content,
            "metadata": self.metadata,
            "is_final": self.is_final,
            "timestamp": self.timestamp,
        }


def _topological_sort(plan_graph: dict[str, Any]) -> list[dict[str, Any]]:
    """Sort plan nodes in dependency order. Nodes with no dependencies come first."""
    nodes = plan_graph.get("nodes", [])
    if not nodes:
        return []

    node_map = {n["id"]: n for n in nodes}
    visited: set[str] = set()
    result: list[dict[str, Any]] = []

    def visit(node_id: str):
        if node_id in visited:
            return
        visited.add(node_id)
        node = node_map.get(node_id)
        if not node:
            return
        for dep_id in node.get("depends_on", []):
            visit(dep_id)
        result.append(node)

    for node in nodes:
        visit(node["id"])

    return result


class MultiAgentOrchestrator:
    """Coordinates Planner, Executor, and Reviewer agents."""

    def __init__(self, llm: Any):
        self.llm = llm
        self.planner = PlannerAgent(llm)
        self.executor = ExecutorAgent(llm)
        self.reviewer = ReviewerAgent(llm)
        self.conversation_history: list[dict[str, str]] = []

    async def run(self, user_query: str) -> AsyncGenerator[AgentEvent, None]:
        """Execute the full multi-agent pipeline, yielding events."""
        step = 0
        runtime_context = await build_runtime_context(user_query)

        # ── Phase 1: Planning ──
        yield AgentEvent(
            type="agent_start", agent="planner",
            content="Planner 正在分析问题并生成执行计划...",
            step_number=step,
        )
        step += 1

        yield AgentEvent(
            type="status",
            agent="orchestrator",
            content=build_runtime_status_text(runtime_context),
            step_number=step,
            metadata={"runtime_context": runtime_context},
        )
        step += 1

        plan_result = await self.planner.plan(user_query, self.conversation_history, runtime_context)
        plan_graph = plan_result.graph

        # Yield planner reasoning
        if plan_result.reasoning:
            yield AgentEvent(
                type="thinking", agent="planner",
                content=plan_result.reasoning,
                step_number=step,
                metadata={"reasoning": plan_result.reasoning},
            )
            step += 1

        if plan_result.source != "llm" or plan_graph.get("source") != "llm":
            yield AgentEvent(
                type="error",
                agent="planner",
                content="Planner 未能生成真实 LLM 计划，本轮已中止，未执行任何保底/写死计划。",
                step_number=step,
                metadata={
                    "plan_source": plan_result.source,
                    "reason": plan_result.reasoning,
                },
                is_final=True,
            )
            return

        # Yield plan
        yield AgentEvent(
            type="plan", agent="planner",
            content=f"已生成执行计划：{plan_graph.get('title', '执行计划')}",
            step_number=step,
            metadata=build_plan_metadata(plan_graph),
        )
        step += 1

        # ── Phase 2 & 3: Execute + Review loop ──
        replan_count = 0
        execution_results: dict[str, ExecutionResult] = {}
        last_plan_sig = plan_graph_signature(plan_graph)

        while replan_count <= MAX_REPLAN_ATTEMPTS and step < MAX_TOTAL_STEPS:
            sorted_nodes = _topological_sort(plan_graph)
            needs_replan = False

            for node in sorted_nodes:
                node_id = node["id"]
                if step >= MAX_TOTAL_STEPS:
                    break

                # Skip already completed nodes
                if node.get("status") == "completed" or node_id in execution_results:
                    continue

                # Mark node in progress
                node["status"] = "in_progress"
                plan_graph["active_node_ids"] = [node_id]

                # Executor start
                yield AgentEvent(
                    type="agent_start", agent="executor",
                    content=f"Executor 正在执行：{node.get('title', '')}",
                    step_number=step,
                    metadata={"node_id": node_id, "node_title": node.get("title", "")},
                )
                step += 1

                # Execute
                exec_result = await self.executor.execute_node(
                    node,
                    execution_results,
                    plan_graph,
                    user_query,
                    runtime_context,
                )
                execution_results[node_id] = exec_result

                # Yield thinking if present
                if exec_result.thinking:
                    yield AgentEvent(
                        type="thinking", agent="executor",
                        content=exec_result.thinking,
                        step_number=step,
                        metadata={"node_id": node_id},
                    )
                    step += 1

                # Yield action + observation if tool was called
                if exec_result.tool_name:
                    action_meta = self.executor.build_action_metadata(exec_result, plan_graph)
                    action_meta["node_id"] = node_id
                    yield AgentEvent(
                        type="action", agent="executor",
                        content=action_meta.get("tool_input_summary", f"调用 {exec_result.tool_name}"),
                        step_number=step,
                        metadata=action_meta,
                    )
                    step += 1

                    obs_meta = self.executor.build_observation_metadata(exec_result, plan_graph)
                    obs_meta["node_id"] = node_id
                    obs_content = obs_meta.get("result_summary", "执行完成")
                    if exec_result.error:
                        obs_content = f"执行错误: {exec_result.error}"
                    yield AgentEvent(
                        type="observation", agent="executor",
                        content=obs_content,
                        step_number=step,
                        metadata=obs_meta,
                    )
                    step += 1

                # Mark completed
                node["status"] = "completed"

                # Emit plan update
                new_sig = plan_graph_signature(plan_graph)
                if new_sig != last_plan_sig:
                    last_plan_sig = new_sig
                    yield AgentEvent(
                        type="plan_update", agent="orchestrator",
                        content="计划状态已更新",
                        step_number=step,
                        metadata=build_plan_metadata(plan_graph),
                    )
                    step += 1

                # ── Phase 3: Review (for query/analysis nodes) ──
                if node.get("kind") in ("query", "analysis") and exec_result.tool_name:
                    yield AgentEvent(
                        type="agent_start", agent="reviewer",
                        content=f"Reviewer 正在审查：{node.get('title', '')}",
                        step_number=step,
                        metadata={"node_id": node_id},
                    )
                    step += 1

                    review = await self.reviewer.review(node, exec_result, user_query)

                    yield AgentEvent(
                        type="review", agent="reviewer",
                        content=review.summary or ("审查通过" if review.verdict == "approve" else "审查未通过"),
                        step_number=step,
                        metadata={
                            "node_id": node_id,
                            "verdict": review.verdict,
                            "review_points": review.review_points,
                            "issues": review.issues,
                            "suggestions": review.suggestions,
                        },
                    )
                    step += 1

                    if review.verdict == "reject" and replan_count < MAX_REPLAN_ATTEMPTS:
                        yield AgentEvent(
                            type="replan_trigger", agent="reviewer",
                            content=f"审查不通过，触发重规划：{review.summary}",
                            step_number=step,
                            metadata={
                                "reason": review.summary,
                                "issues": review.issues,
                                "original_node_id": node_id,
                            },
                        )
                        step += 1

                        # Replan
                        yield AgentEvent(
                            type="agent_start", agent="planner",
                            content="Planner 正在根据审查反馈修订计划...",
                            step_number=step,
                        )
                        step += 1

                        replan_result = await self.planner.replan(
                            user_query,
                            plan_graph,
                            review.to_dict(),
                            {"completed_nodes": list(execution_results.keys())},
                            runtime_context,
                        )
                        plan_graph = replan_result.graph
                        replan_count += 1

                        if replan_result.reasoning:
                            yield AgentEvent(
                                type="thinking", agent="planner",
                                content=replan_result.reasoning,
                                step_number=step,
                            )
                            step += 1

                        if replan_result.source != "llm" or plan_graph.get("source") != "llm":
                            yield AgentEvent(
                                type="error",
                                agent="planner",
                                content="Planner 未能基于审查反馈生成真实重规划，本轮已中止，未继续执行保底计划。",
                                step_number=step,
                                metadata={
                                    "plan_source": replan_result.source,
                                    "reason": replan_result.reasoning,
                                    "original_node_id": node_id,
                                },
                                is_final=True,
                            )
                            return

                        yield AgentEvent(
                            type="plan_update", agent="planner",
                            content=f"计划已修订：{plan_graph.get('change_reason', '')}",
                            step_number=step,
                            metadata=build_plan_metadata(plan_graph),
                        )
                        step += 1
                        last_plan_sig = plan_graph_signature(plan_graph)

                        needs_replan = True
                        break  # Restart execution loop with new plan

            if not needs_replan:
                break  # All nodes completed

        # ── Phase 4: Final synthesis ──
        yield AgentEvent(
            type="agent_start", agent="reviewer",
            content="Reviewer 正在汇总分析结果并生成最终报告...",
            step_number=step,
        )
        step += 1

        synthesis = await self.reviewer.synthesize(user_query, execution_results, plan_graph)

        # Mark all nodes completed in final plan update
        for node in plan_graph.get("nodes", []):
            if node.get("status") != "skipped":
                node["status"] = "completed"
        plan_graph["active_node_ids"] = []

        yield AgentEvent(
            type="plan_update", agent="orchestrator",
            content="所有步骤已完成",
            step_number=step,
            metadata=build_plan_metadata(plan_graph),
        )
        step += 1

        yield AgentEvent(
            type="answer", agent="reviewer",
            content=synthesis.answer,
            step_number=step,
            metadata={"evidence": synthesis.evidence},
            is_final=True,
        )

        # Update conversation history
        self.conversation_history.append({"role": "user", "content": user_query})
        self.conversation_history.append({"role": "assistant", "content": synthesis.answer})
        # Keep history bounded
        if len(self.conversation_history) > 20:
            self.conversation_history = self.conversation_history[-20:]
