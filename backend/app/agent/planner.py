"""Model-driven planning for the ReAct agent."""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from app.agent.plan_presentation import build_fallback_plan_graph, normalize_plan_graph

PLANNER_SYSTEM_PROMPT = """
你是一个“执行计划图生成器”，服务于税务/账务/对账分析 Agent。

你的唯一任务是输出一个紧凑、可执行、可更新的 JSON 计划图。
要求：
1. 只能输出 JSON，不要 Markdown，不要解释。
2. 节点数控制在 4 到 6 个，必须紧凑，不能把每个微动作都拆成节点。
3. 节点标题必须是短中文，并且要贴合当前问题语义，不要泛泛写“查询业务数据”“查看业务表结构”，除非上下文真的不知道主题。
3.1 如果用户问的是“多少张表 / 有哪些表 / 某张表有哪些字段 / schema / metadata”，计划图必须围绕元数据检查展开，不要擅自扩展成税务对账分析。
3.2 如果用户问的是简单直接的事实问题，计划图应尽量短，并指向一到两次工具调用即可完成。
4. 若已知是税务、账务、税账差异、风险、表结构、指标汇总、规则核对等，要直接写进节点标题。
5. 初始规划和更新规划都要尽量保留稳定的节点 id，避免每轮全量重命名。
6. 节点 kind 只能是：goal、schema、query、analysis、knowledge、visualization、answer、task。
7. 节点 status 只能是：pending、in_progress、completed、skipped、blocked。
8. active_node_ids 只保留当前应该推进的 1 到 2 个节点。
9. 若路径变化，要在 change_reason 中简洁说明为什么要改计划。
10. 计划图必须服务于真实执行，不要为了好看增加无用节点。

输出 JSON 结构：
{
  "title": "本轮计划标题",
  "summary": "一句话说明当前整体策略",
  "nodes": [
    {
      "id": "n1",
      "title": "短中文标题",
      "detail": "节点要做什么，为什么做",
      "status": "completed",
      "kind": "goal",
      "depends_on": [],
      "tool_hints": ["metadata_query"],
      "done_when": "什么时候算完成"
    }
  ],
  "edges": [{"source": "n1", "target": "n2"}],
  "active_node_ids": ["n2"],
 "change_reason": "可选，若无变化可为空"
}

示例：
- 用户问“当前系统有多少张表？”
  合理节点示例：识别元数据问题 -> 查看系统表清单 -> 汇总结论
- 用户问“tax_vat_declaration 有哪些字段？”
  合理节点示例：确认目标表 -> 查看表结构 -> 汇总结论
""".strip()


async def generate_initial_plan(
    llm: Any,
    user_query: str,
    conversation_history: list[dict[str, Any]],
) -> dict[str, Any]:
    payload = {
        "mode": "initial",
        "user_query": user_query,
        "conversation_history": trim_conversation_history(conversation_history),
    }
    return await _run_planner(llm, payload, user_query=user_query)


async def update_plan_graph(
    llm: Any,
    user_query: str,
    current_plan: dict[str, Any],
    recent_execution: dict[str, Any],
) -> dict[str, Any]:
    payload = {
        "mode": "update",
        "user_query": user_query,
        "current_plan": current_plan,
        "recent_execution": recent_execution,
    }
    return await _run_planner(llm, payload, user_query=user_query)


async def _run_planner(llm: Any, payload: dict[str, Any], user_query: str) -> dict[str, Any]:
    raw_content = ""
    try:
        response = await asyncio.wait_for(
            llm.chat(
                messages=[
                    {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
                stream=False,
                temperature=0.0,
                max_tokens=900,
                response_format={"type": "json_object"},
            ),
            timeout=25,
        )
        raw_content = response.choices[0].message.content or ""
        plan = parse_plan_json(raw_content)
        if not plan:
            raise ValueError("planner returned non-JSON or empty JSON")
        normalized = normalize_plan_graph(plan, user_query=user_query)
        normalized["source"] = "llm"
        return normalized
    except Exception as exc:
        append_planner_debug_log(user_query=user_query, payload=payload, raw_content=raw_content, error=str(exc))
        return build_fallback_plan_graph(user_query)


def parse_plan_json(content: str) -> dict[str, Any]:
    text = (content or "").strip()
    if not text:
        return {}

    fenced = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE | re.DOTALL).strip()
    candidates = [fenced]

    match = re.search(r"\{.*\}", fenced, flags=re.DOTALL)
    if match:
        candidates.append(match.group(0))

    for candidate in candidates:
        try:
            value = json.loads(candidate)
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError:
            repaired = repair_truncated_json(candidate)
            if repaired and repaired != candidate:
                try:
                    value = json.loads(repaired)
                    if isinstance(value, dict):
                        return value
                except json.JSONDecodeError:
                    continue
    return {}


def repair_truncated_json(text: str) -> str:
    candidate = (text or "").strip()
    if not candidate:
        return ""

    candidate = candidate.rstrip()
    while candidate and candidate[-1] in ",:":
        candidate = candidate[:-1].rstrip()

    stack: list[str] = []
    in_string = False
    escape = False
    last_safe_index = -1

    for index, char in enumerate(candidate):
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == "\"":
                in_string = False
                last_safe_index = index
            continue

        if char == "\"":
            in_string = True
        elif char in "{[":
            stack.append(char)
            last_safe_index = index
        elif char == "}":
            if stack and stack[-1] == "{":
                stack.pop()
                last_safe_index = index
            else:
                break
        elif char == "]":
            if stack and stack[-1] == "[":
                stack.pop()
                last_safe_index = index
            else:
                break
        else:
            last_safe_index = index

    if in_string and last_safe_index >= 0:
        candidate = candidate[: last_safe_index + 1].rstrip()
        while candidate and candidate[-1] in ",:":
            candidate = candidate[:-1].rstrip()

        stack = []
        in_string = False
        escape = False
        for char in candidate:
            if in_string:
                if escape:
                    escape = False
                elif char == "\\":
                    escape = True
                elif char == "\"":
                    in_string = False
                continue
            if char == "\"":
                in_string = True
            elif char in "{[":
                stack.append(char)
            elif char == "}" and stack and stack[-1] == "{":
                stack.pop()
            elif char == "]" and stack and stack[-1] == "[":
                stack.pop()

    closers = []
    for opener in reversed(stack):
        closers.append("}" if opener == "{" else "]")

    return candidate + "".join(closers)


def trim_conversation_history(history: list[dict[str, Any]]) -> list[dict[str, str]]:
    trimmed: list[dict[str, str]] = []
    for item in history[-6:]:
        role = str(item.get("role") or "")
        content = str(item.get("content") or "").strip()
        if role not in {"user", "assistant"} or not content:
            continue
        trimmed.append({"role": role, "content": content[:1200]})
    return trimmed


def append_planner_debug_log(
    user_query: str,
    payload: dict[str, Any],
    raw_content: str,
    error: str,
) -> None:
    log_path = Path("D:/lsy_projects/tda_tdp_poc/backend-planner-debug.log")
    record = {
        "ts": datetime.now().isoformat(),
        "user_query": user_query,
        "payload": payload,
        "raw_content": raw_content[:4000],
        "error": error,
    }
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


PLANNER_SYSTEM_PROMPT = """
你是“执行计划图生成器”，只负责为当前问题生成结构化 JSON 计划图。

重要要求：
1. 只输出 JSON，不要输出 Markdown，不要解释。
2. 计划图必须严格贴合当前用户问题，不要套用税务对账的默认模板。
3. 如果用户问的是“当前系统有多少张表 / 有哪些表 / 某张表有哪些字段 / schema / metadata”，计划图必须围绕元数据查询展开，不要擅自变成税务业务分析。
4. 如果用户问的是简单直接的问题，节点数保持 2 到 4 个即可，不要把每个小动作拆成很多节点。
5. 节点标题必须是简短中文，并且要和当前问题语义一致，例如：
   - “统计系统表数量”
   - “查看表字段结构”
   - “汇总结论”
6. kind 只能是：goal, schema, query, analysis, knowledge, visualization, answer, task
7. status 只能是：pending, in_progress, completed, skipped, blocked
8. active_node_ids 只保留当前应该推进的 1 到 2 个节点。
9. 默认优先考虑真实可执行的工具路径：
   - 元数据问题 -> metadata_query
   - 指标/聚合问题 -> semantic_query
   - 语义层无法表达时 -> sql_executor

输出格式：
{
  "title": "本轮计划标题",
  "summary": "一句话说明整体策略",
  "nodes": [
    {
      "id": "n1",
      "title": "短中文标题",
      "detail": "这一步做什么，为什么做",
      "status": "completed",
      "kind": "goal",
      "depends_on": [],
      "tool_hints": ["metadata_query"],
      "done_when": "什么时候算完成"
    }
  ],
  "edges": [{"source": "n1", "target": "n2"}],
  "active_node_ids": ["n2"],
  "change_reason": ""
}

示例 1：
用户问题：当前系统有多少张表？
合理计划：
- 识别元数据问题
- 统计系统表数量
- 汇总结论

示例 2：
用户问题：tax_vat_declaration 有哪些字段？
合理计划：
- 确认目标表
- 查看表字段结构
- 汇总结论
""".strip()
