from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.agent.planner_agent_v2 import PlannerAgent
from app.agent.runtime_context import build_runtime_context, validate_plan_graph
from app.agent.semantic_grounding import build_semantic_grounding
from app.agent.understanding_agent import UnderstandingAgent
from app.llm.client import get_llm_client


DEFAULT_QUERIES = [
    "分析华兴科技 2024Q3 增值税申报收入与账面收入差异，先给我计划",
    "查看华兴科技 2024 年所得税汇算清缴桥接，重点看应纳税所得额和应补退税额，先给我计划",
    "查看华兴科技 2024Q3 增值税申报诊断，分析进项、销项和转出对税负的影响，先给我计划",
]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run live planner regression against real LLM output.")
    parser.add_argument(
        "--query",
        action="append",
        dest="queries",
        help="One business question to run. Can be provided multiple times.",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="How many times to repeat each query.",
    )
    parser.add_argument(
        "--out",
        default="D:/lsy_projects/tda_tdp_poc/backend-live-planner-regression.json",
        help="Where to write the JSON report.",
    )
    return parser.parse_args()


def _summarize_relevant_models(runtime_context: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in (runtime_context.get("relevant_models") or [])[:6]:
        rows.append(
            {
                "name": item.get("name"),
                "recommended_tool": item.get("recommended_tool"),
                "semantic_kind": item.get("semantic_kind"),
                "query_hints": item.get("query_hints"),
                "metrics": item.get("metrics"),
                "dimensions": item.get("dimensions"),
            }
        )
    return rows


def _summarize_business_nodes(graph: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for node in graph.get("nodes") or []:
        if node.get("kind") not in {"query", "analysis"}:
            continue
        binding = node.get("semantic_binding") or {}
        rows.append(
            {
                "id": node.get("id"),
                "title": node.get("title"),
                "kind": node.get("kind"),
                "tool_hints": node.get("tool_hints"),
                "entry_model": binding.get("entry_model"),
                "supporting_models": binding.get("supporting_models"),
                "metrics": binding.get("metrics"),
                "dimensions": binding.get("dimensions"),
                "entity_filters": binding.get("entity_filters"),
                "resolved_filters": binding.get("resolved_filters"),
                "query_language": binding.get("query_language"),
                "time_context": binding.get("time_context"),
            }
        )
    return rows


def _has_mql_path(business_nodes: list[dict[str, Any]]) -> bool:
    for node in business_nodes:
        tool_hints = node.get("tool_hints") or []
        if "mql_query" in tool_hints:
            return True
        if str(node.get("query_language") or "").strip().lower() == "tda_mql":
            return True
    return False


async def _run_once(query: str, repeat_index: int) -> dict[str, Any]:
    llm = get_llm_client()
    understanding_agent = UnderstandingAgent(llm)
    planner = PlannerAgent(llm)

    grounding = await build_semantic_grounding(query)
    understanding = await understanding_agent.understand(query, [], grounding)
    runtime_context = await build_runtime_context(query, understanding.to_dict(), grounding)
    plan_result = await planner.plan(
        query,
        [],
        runtime_context,
        understanding_result=understanding.to_dict(),
    )

    business_nodes = _summarize_business_nodes(plan_result.graph)
    validation_issues = validate_plan_graph(plan_result.graph, runtime_context)
    return {
        "query": query,
        "repeat_index": repeat_index,
        "understanding": understanding.to_dict(),
        "runtime_context_summary": {
            "query_mode": runtime_context.get("query_mode"),
            "period_hints": runtime_context.get("period_hints"),
            "enterprise_candidates": runtime_context.get("enterprise_candidates"),
            "relevant_models": _summarize_relevant_models(runtime_context),
        },
        "plan_source": plan_result.source,
        "reasoning": plan_result.reasoning,
        "validation_issues": validation_issues,
        "business_nodes": business_nodes,
        "has_mql_path": _has_mql_path(business_nodes),
        "full_plan": plan_result.graph,
    }


async def _main() -> int:
    args = _parse_args()
    queries = args.queries or DEFAULT_QUERIES
    repeat = max(args.repeat, 1)

    results: list[dict[str, Any]] = []
    for query in queries:
        for repeat_index in range(1, repeat + 1):
            results.append(await _run_once(query, repeat_index))

    report = {
        "summary": {
            "total_runs": len(results),
            "llm_plan_runs": sum(1 for item in results if item["plan_source"] == "llm"),
            "fallback_runs": sum(1 for item in results if item["plan_source"] == "fallback"),
            "mql_path_runs": sum(1 for item in results if item["has_mql_path"]),
        },
        "results": results,
    }

    out_path = Path(args.out)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(report["summary"], ensure_ascii=False))
    print(str(out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
