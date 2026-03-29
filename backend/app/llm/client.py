"""统一 LLM 客户端 — 兼容 OpenAI 协议 (GPT/GLM/DeepSeek)"""
import json
from typing import AsyncGenerator, Optional
from openai import AsyncOpenAI
from app.config import get_settings

settings = get_settings()


class LLMClient:
    """统一的大模型访问客户端，遵循 OpenAI 协议"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self._client = AsyncOpenAI(
            api_key=api_key or settings.LLM_API_KEY,
            base_url=base_url or settings.LLM_BASE_URL,
        )
        self.model = model or settings.LLM_MODEL
        self.temperature = settings.LLM_TEMPERATURE

    async def chat(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        stream: bool = False,
        temperature: Optional[float] = None,
        **extra_kwargs,
    ):
        """聊天补全，支持工具调用和流式输出"""
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature or self.temperature,
            "stream": stream,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        kwargs.update(extra_kwargs)

        response = await self._client.chat.completions.create(**kwargs)
        return response

    async def chat_stream(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        temperature: Optional[float] = None,
    ) -> AsyncGenerator[dict, None]:
        """流式聊天，逐块返回内容"""
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature or self.temperature,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        stream = await self._client.chat.completions.create(**kwargs)

        collected_content = ""
        collected_tool_calls = []

        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if not delta:
                continue

            # 文本内容
            if delta.content:
                collected_content += delta.content
                yield {"type": "content", "content": delta.content}

            # 工具调用
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    if tc.index is not None:
                        while len(collected_tool_calls) <= tc.index:
                            collected_tool_calls.append({
                                "id": "", "function": {"name": "", "arguments": ""}
                            })
                        if tc.id:
                            collected_tool_calls[tc.index]["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                collected_tool_calls[tc.index]["function"]["name"] = tc.function.name
                            if tc.function.arguments:
                                collected_tool_calls[tc.index]["function"]["arguments"] += tc.function.arguments

            # 结束
            if chunk.choices[0].finish_reason:
                yield {
                    "type": "done",
                    "finish_reason": chunk.choices[0].finish_reason,
                    "content": collected_content,
                    "tool_calls": collected_tool_calls if collected_tool_calls else None,
                }


# 全局单例
_llm_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client
