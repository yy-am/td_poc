"""StageGraph v1-lite primitives for the orchestration flow."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


STAGE_DEFINITIONS = (
    ("intent_recognition", "意图识别", "识别问题目标、企业、期间和分析意图。"),
    ("semantic_binding", "语义绑定", "绑定候选语义资产、指标、维度与实体过滤条件。"),
    ("tda_mql_draft", "TDA-MQL 草拟", "整理受控的 TDA-MQL 查询骨架与语义草稿。"),
    ("feasibility_assessment", "可行性评估", "检查当前语义资产、实体解析和执行约束是否可落地。"),
    ("planning", "计划生成", "由 Planner 生成并校验可执行计划。"),
    ("metric_execution", "指标执行", "执行指标类查询、聚合分析和常规语义取数。"),
    ("detail_execution", "明细下钻", "执行明细穿透或下钻节点。"),
    ("evidence_verification", "证据校验", "核对结果是否有足够证据支持后续判断。"),
    ("review", "结果审查", "审查关键结果、问题覆盖度和可交付性。"),
    ("report_generation", "报告生成", "汇总证据并生成最终回答。"),
)


@dataclass
class StageState:
    stage_id: str
    title: str
    detail: str
    status: str = "pending"
    note: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class StageGraphTracker:
    """Maintains an explicit StageGraph over the current flow."""

    def __init__(self) -> None:
        self._states = {
            stage_id: StageState(stage_id=stage_id, title=title, detail=detail)
            for stage_id, title, detail in STAGE_DEFINITIONS
        }

    def mark_in_progress(
        self,
        stage_id: str,
        *,
        note: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._update(stage_id, status="in_progress", note=note, metadata=metadata)

    def mark_completed(
        self,
        stage_id: str,
        *,
        note: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._update(stage_id, status="completed", note=note, metadata=metadata)

    def mark_blocked(
        self,
        stage_id: str,
        *,
        note: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._update(stage_id, status="blocked", note=note, metadata=metadata)

    def mark_skipped(
        self,
        stage_id: str,
        *,
        note: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._update(stage_id, status="skipped", note=note, metadata=metadata)

    def current_status(self, stage_id: str) -> str:
        return self._states[stage_id].status

    def snapshot(self) -> dict[str, Any]:
        nodes = []
        for stage_id, _, _ in STAGE_DEFINITIONS:
            state = self._states[stage_id]
            detail = state.detail
            if state.note:
                detail = f"{detail}\n当前说明：{state.note}"
            nodes.append(
                {
                    "id": state.stage_id,
                    "title": state.title,
                    "detail": detail,
                    "status": state.status,
                    "kind": "task",
                    "depends_on": self._depends_on(stage_id),
                    "tool_hints": [],
                    "done_when": state.note,
                    "stage_metadata": dict(state.metadata),
                }
            )

        edges = []
        for index in range(1, len(STAGE_DEFINITIONS)):
            edges.append(
                {
                    "source": STAGE_DEFINITIONS[index - 1][0],
                    "target": STAGE_DEFINITIONS[index][0],
                }
            )

        active_stage_ids = [
            stage_id for stage_id, state in self._states.items() if state.status == "in_progress"
        ]
        return {
            "title": "StageGraph v1-lite",
            "summary": "将当前多智能体执行流显式映射为更细粒度的分析阶段。",
            "nodes": nodes,
            "edges": edges,
            "active_node_ids": active_stage_ids,
            "source": "stage_graph_v1_lite",
        }

    def _update(
        self,
        stage_id: str,
        *,
        status: str,
        note: str,
        metadata: dict[str, Any] | None,
    ) -> None:
        state = self._states[stage_id]
        state.status = status
        if note:
            state.note = note
        if metadata is not None:
            state.metadata = dict(metadata)

    @staticmethod
    def _depends_on(stage_id: str) -> list[str]:
        order = [item[0] for item in STAGE_DEFINITIONS]
        index = order.index(stage_id)
        if index == 0:
            return []
        return [order[index - 1]]
