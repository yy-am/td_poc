from __future__ import annotations

from app.agent.stage_graph import StageGraphTracker


def test_stage_graph_tracker_marks_and_snapshots_stage_progress():
    tracker = StageGraphTracker()

    tracker.mark_in_progress("intent_recognition", note="识别企业与期间")
    tracker.mark_completed("intent_recognition", note="已识别华兴科技 2024Q3")
    tracker.mark_in_progress("planning", note="Planner 正在生成计划")

    snapshot = tracker.snapshot()
    node_by_id = {node["id"]: node for node in snapshot["nodes"]}

    assert snapshot["title"] == "StageGraph v1-lite"
    assert snapshot["active_node_ids"] == ["planning"]
    assert node_by_id["intent_recognition"]["status"] == "completed"
    assert "华兴科技 2024Q3" in node_by_id["intent_recognition"]["detail"]
    assert node_by_id["planning"]["status"] == "in_progress"


def test_stage_graph_tracker_can_mark_blocked_and_skipped():
    tracker = StageGraphTracker()

    tracker.mark_blocked("planning", note="LLM 计划校验失败")
    tracker.mark_skipped("review", note="当前阶段无需审查")

    snapshot = tracker.snapshot()
    node_by_id = {node["id"]: node for node in snapshot["nodes"]}

    assert node_by_id["planning"]["status"] == "blocked"
    assert node_by_id["review"]["status"] == "skipped"
