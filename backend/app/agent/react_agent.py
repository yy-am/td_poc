"""ReAct Agent 核心 — 思考-行动-观察循环

关键特性:
1. 每一步(thinking/action/observation)都实时推送给前端
2. 最多10轮循环防止无限执行
3. 支持多工具调用
4. 结果包含文本答案+可选图表+可选数据表
"""
import json
import time
from typing import AsyncGenerator, Optional
from datetime import datetime
from app.agent.system_prompt import build_system_prompt
from app.llm.client import get_llm_client
from app.mcp.tools.registry import TOOL_DEFINITIONS, TOOL_FUNCTIONS


class AgentStep:
    """Agent 推理步骤"""
    def __init__(self, type: str, content: str, step_number: int = 0,
                 metadata: Optional[dict] = None, is_final: bool = False):
        self.type = type
        self.content = content
        self.step_number = step_number
        self.metadata = metadata or {}
        self.is_final = is_final
        self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "step_number": self.step_number,
            "content": self.content,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
            "is_final": self.is_final,
        }


class ReactAgent:
    """ReAct Agent — 核心推理引擎"""
    MAX_STEPS = 10

    def __init__(self, session_id: str = "default"):
        self.session_id = session_id
        self.llm = get_llm_client()
        self.conversation_history: list[dict] = []

    async def run(self, user_query: str) -> AsyncGenerator[AgentStep, None]:
        """执行 ReAct 循环，逐步 yield AgentStep"""
        step_num = 0

        # 状态通知
        yield AgentStep(type="status", content="正在分析您的问题...", step_number=step_num)

        # 构建系统提示词
        system_prompt = build_system_prompt()
        messages = [
            {"role": "system", "content": system_prompt},
            *self.conversation_history,
            {"role": "user", "content": user_query},
        ]

        for step in range(self.MAX_STEPS):
            step_num = step + 1
            start_time = time.time()

            try:
                # 调用LLM (非流式，便于解析tool_calls)
                response = await self.llm.chat(
                    messages=messages,
                    tools=TOOL_DEFINITIONS,
                    stream=False,
                )
            except Exception as e:
                yield AgentStep(
                    type="error", content=f"LLM调用失败: {str(e)}",
                    step_number=step_num, is_final=True,
                )
                return

            choice = response.choices[0]
            message = choice.message
            duration_ms = int((time.time() - start_time) * 1000)

            # 将助手消息加入上下文
            msg_dict = {"role": "assistant", "content": message.content or ""}
            if message.tool_calls:
                msg_dict["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in message.tool_calls
                ]
            messages.append(msg_dict)

            # THINKING: 如果有文本内容，作为思考步骤输出
            if message.content:
                yield AgentStep(
                    type="thinking", content=message.content, step_number=step_num,
                    metadata={"duration_ms": duration_ms},
                )

            # 检查是否有工具调用
            if not message.tool_calls:
                # 没有工具调用 = 最终答案
                final_content = message.content or "分析完成。"
                yield AgentStep(
                    type="answer", content=final_content,
                    step_number=step_num, is_final=True,
                )
                # 保存到对话历史
                self.conversation_history.append({"role": "user", "content": user_query})
                self.conversation_history.append({"role": "assistant", "content": final_content})
                return

            # ACTION + OBSERVATION: 执行每个工具调用
            for tc in message.tool_calls:
                tool_name = tc.function.name
                try:
                    tool_args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    tool_args = {}

                # 推送 ACTION 步骤
                yield AgentStep(
                    type="action", content=f"调用工具: {tool_name}",
                    step_number=step_num,
                    metadata={"tool_name": tool_name, "tool_input": tool_args},
                )

                # 执行工具
                tool_fn = TOOL_FUNCTIONS.get(tool_name)
                if tool_fn:
                    try:
                        tool_start = time.time()
                        result = await tool_fn(**tool_args)
                        tool_duration = int((time.time() - tool_start) * 1000)
                    except Exception as e:
                        result = {"error": f"工具执行出错: {str(e)}"}
                        tool_duration = 0
                else:
                    result = {"error": f"未知工具: {tool_name}"}
                    tool_duration = 0

                result_str = json.dumps(result, ensure_ascii=False, default=str)

                # 构建 observation 元数据
                obs_metadata = {"tool_name": tool_name, "duration_ms": tool_duration}
                if tool_name == "sql_executor" and "sql" in result:
                    obs_metadata["sql"] = result["sql"]
                if tool_name == "chart_generator" and "chart_config" in result:
                    obs_metadata["chart_config"] = result["chart_config"]
                if "columns" in result and "rows" in result:
                    obs_metadata["table_data"] = {
                        "columns": result["columns"],
                        "rows": result["rows"][:20],  # 前端预览前20行
                    }

                # 推送 OBSERVATION 步骤
                # 截断过长的结果文本
                display_content = result_str if len(result_str) < 2000 else result_str[:2000] + "... (数据已截断)"
                yield AgentStep(
                    type="observation", content=display_content,
                    step_number=step_num, metadata=obs_metadata,
                )

                # 将工具结果加入上下文
                messages.append({
                    "role": "tool",
                    "content": result_str[:8000],  # 限制给LLM的长度
                    "tool_call_id": tc.id,
                })

        # 达到最大步数
        yield AgentStep(
            type="answer", content="已达到最大推理步数，请尝试更具体的问题。",
            step_number=step_num + 1, is_final=True,
        )
