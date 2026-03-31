"""Unified LLM client (OpenAI-compatible)."""

from __future__ import annotations

import asyncio
import json
from contextvars import ContextVar, Token
from datetime import datetime
from typing import Any, AsyncGenerator, Callable, Optional

from openai import APIConnectionError, APITimeoutError, AsyncOpenAI

from app.config import get_settings

settings = get_settings()
TRANSIENT_LLM_ERRORS = (APIConnectionError, APITimeoutError)
TRANSIENT_LLM_RETRY_DELAYS = (0.5, 1.0)

_TRACE_SINK_VAR: ContextVar[list[dict[str, Any]] | None] = ContextVar("llm_trace_sink", default=None)
_TRACE_META_PROVIDER_VAR: ContextVar[Callable[[], dict[str, Any]] | None] = ContextVar(
    "llm_trace_meta_provider", default=None
)
_TRACE_SEQ_VAR: ContextVar[int] = ContextVar("llm_trace_seq", default=0)


class LLMClient:
    """Unified large-model access client using Chat Completions API."""

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
        self.retry_delays = TRANSIENT_LLM_RETRY_DELAYS

    async def _create_completion_with_retry(self, **kwargs):
        """Only retry transient transport failures; keep semantic failures explicit."""
        last_error: Exception | None = None

        for attempt, delay in enumerate((0.0, *self.retry_delays), start=1):
            if delay > 0:
                await asyncio.sleep(delay)
            try:
                return await self._client.chat.completions.create(**kwargs)
            except TRANSIENT_LLM_ERRORS as exc:
                last_error = exc
                if attempt > len(self.retry_delays):
                    raise

        raise last_error or RuntimeError("LLM completion failed without a captured error")

    @staticmethod
    def _truncate_text(value: Any, limit: int = 240) -> str:
        text = str(value or "").strip()
        if len(text) <= limit:
            return text
        return text[: limit - 3].rstrip() + "..."

    @staticmethod
    def _extract_message_content(response: Any) -> str:
        try:
            return str(response.choices[0].message.content or "").strip()
        except Exception:
            return ""

    def _extract_reasoning_text(self, content: str) -> str:
        text = str(content or "").strip()
        if not text:
            return ""
        try:
            parsed = json.loads(text)
        except Exception:
            return self._truncate_text(text, 600)

        if not isinstance(parsed, dict):
            return self._truncate_text(text, 600)

        for key in ("reasoning", "analysis", "summary", "intent_summary", "business_goal"):
            value = str(parsed.get(key) or "").strip()
            if value:
                return self._truncate_text(value, 600)
        return self._truncate_text(text, 600)

    def _record_trace(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]],
        extra_trace: Optional[dict[str, Any]],
        kwargs: dict[str, Any],
        response: Any,
    ) -> None:
        sink = _TRACE_SINK_VAR.get()
        if sink is None:
            return

        seq = _TRACE_SEQ_VAR.get() + 1
        _TRACE_SEQ_VAR.set(seq)

        content = self._extract_message_content(response)
        reasoning = self._extract_reasoning_text(content)
        if not reasoning:
            reasoning = "Model returned no textual reasoning for this call."
        system_prompt = ""
        user_prompt = ""
        if messages:
            for item in messages:
                role = str(item.get("role") or "")
                if role == "system" and not system_prompt:
                    system_prompt = self._truncate_text(item.get("content"), 240)
                if role == "user":
                    user_prompt = self._truncate_text(item.get("content"), 280)

        provider = _TRACE_META_PROVIDER_VAR.get()
        provider_meta = provider() if provider else {}
        if not isinstance(provider_meta, dict):
            provider_meta = {}
        if not isinstance(extra_trace, dict):
            extra_trace = {}

        sink.append(
            {
                "llm_call_index": seq,
                "timestamp": datetime.now().isoformat(),
                "model": kwargs.get("model") or self.model,
                "temperature": kwargs.get("temperature"),
                "max_tokens": kwargs.get("max_tokens"),
                "tool_count": len(tools or []),
                "stage_id": str(provider_meta.get("stage_id") or "").strip(),
                "agent": str(extra_trace.get("agent") or "").strip(),
                "operation": str(extra_trace.get("operation") or "").strip(),
                "node_id": str(extra_trace.get("node_id") or "").strip(),
                "node_title": str(extra_trace.get("node_title") or "").strip(),
                "system_prompt_preview": system_prompt,
                "user_prompt_preview": user_prompt,
                "thinking": reasoning,
                "raw_content_preview": self._truncate_text(content, 900),
            }
        )

    def _record_failed_trace(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]],
        extra_trace: Optional[dict[str, Any]],
        kwargs: dict[str, Any],
        error: BaseException,
    ) -> None:
        sink = _TRACE_SINK_VAR.get()
        if sink is None:
            return

        seq = _TRACE_SEQ_VAR.get() + 1
        _TRACE_SEQ_VAR.set(seq)

        system_prompt = ""
        user_prompt = ""
        if messages:
            for item in messages:
                role = str(item.get("role") or "")
                if role == "system" and not system_prompt:
                    system_prompt = self._truncate_text(item.get("content"), 240)
                if role == "user":
                    user_prompt = self._truncate_text(item.get("content"), 280)

        provider = _TRACE_META_PROVIDER_VAR.get()
        provider_meta = provider() if provider else {}
        if not isinstance(provider_meta, dict):
            provider_meta = {}
        if not isinstance(extra_trace, dict):
            extra_trace = {}

        sink.append(
            {
                "llm_call_index": seq,
                "timestamp": datetime.now().isoformat(),
                "model": kwargs.get("model") or self.model,
                "temperature": kwargs.get("temperature"),
                "max_tokens": kwargs.get("max_tokens"),
                "tool_count": len(tools or []),
                "stage_id": str(provider_meta.get("stage_id") or "").strip(),
                "agent": str(extra_trace.get("agent") or "").strip(),
                "operation": str(extra_trace.get("operation") or "").strip(),
                "node_id": str(extra_trace.get("node_id") or "").strip(),
                "node_title": str(extra_trace.get("node_title") or "").strip(),
                "system_prompt_preview": system_prompt,
                "user_prompt_preview": user_prompt,
                "thinking": f"LLM 调用失败：{type(error).__name__}: {self._truncate_text(error, 220)}",
                "raw_content_preview": "",
                "error": {
                    "type": type(error).__name__,
                    "message": self._truncate_text(error, 500),
                },
            }
        )

    def begin_trace(
        self,
        sink: list[dict[str, Any]],
        *,
        meta_provider: Callable[[], dict[str, Any]] | None = None,
    ) -> tuple[Token, Token, Token]:
        sink_token = _TRACE_SINK_VAR.set(sink)
        meta_token = _TRACE_META_PROVIDER_VAR.set(meta_provider)
        seq_token = _TRACE_SEQ_VAR.set(0)
        return sink_token, meta_token, seq_token

    def end_trace(self, tokens: tuple[Token, Token, Token]) -> None:
        sink_token, meta_token, seq_token = tokens
        _TRACE_SEQ_VAR.reset(seq_token)
        _TRACE_META_PROVIDER_VAR.reset(meta_token)
        _TRACE_SINK_VAR.reset(sink_token)

    async def chat(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        stream: bool = False,
        temperature: Optional[float] = None,
        trace: Optional[dict[str, Any]] = None,
        **extra_kwargs,
    ):
        """Chat completion with optional tool-calling."""
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

        try:
            response = await self._create_completion_with_retry(**kwargs)
        except asyncio.CancelledError as exc:
            self._record_failed_trace(
                messages=messages,
                tools=tools,
                extra_trace=trace,
                kwargs=kwargs,
                error=exc,
            )
            raise
        except Exception as exc:
            self._record_failed_trace(
                messages=messages,
                tools=tools,
                extra_trace=trace,
                kwargs=kwargs,
                error=exc,
            )
            raise
        if not stream:
            self._record_trace(
                messages=messages,
                tools=tools,
                extra_trace=trace,
                kwargs=kwargs,
                response=response,
            )
        return response

    async def chat_stream(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        temperature: Optional[float] = None,
    ) -> AsyncGenerator[dict, None]:
        """Streaming chat, yields content and tool chunks."""
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

            if delta.content:
                collected_content += delta.content
                yield {"type": "content", "content": delta.content}

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

            if chunk.choices[0].finish_reason:
                yield {
                    "type": "done",
                    "finish_reason": chunk.choices[0].finish_reason,
                    "content": collected_content,
                    "tool_calls": collected_tool_calls if collected_tool_calls else None,
                }


_llm_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client
