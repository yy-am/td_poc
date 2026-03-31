from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
from openai import APIConnectionError, APITimeoutError

from app.llm.client import LLMClient


def _stub_completion_client(create_callable):
    return SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=create_callable,
            )
        )
    )


@pytest.mark.asyncio
async def test_chat_retries_transient_connection_errors_then_succeeds(monkeypatch):
    client = LLMClient(api_key="test", base_url="https://example.com/v1", model="demo")
    request = httpx.Request("POST", "https://example.com/v1/chat/completions")
    response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))])
    calls = {"count": 0}
    sleeps: list[float] = []

    async def fake_sleep(delay: float):
        sleeps.append(delay)

    async def fake_create(**kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise APIConnectionError(message="boom", request=request)
        return response

    monkeypatch.setattr("app.llm.client.asyncio.sleep", fake_sleep)
    client._client = _stub_completion_client(fake_create)

    result = await client.chat(messages=[{"role": "user", "content": "hello"}], stream=False)

    assert result is response
    assert calls["count"] == 2
    assert sleeps == [0.5]


@pytest.mark.asyncio
async def test_chat_retries_timeout_errors_until_exhausted(monkeypatch):
    client = LLMClient(api_key="test", base_url="https://example.com/v1", model="demo")
    request = httpx.Request("POST", "https://example.com/v1/chat/completions")
    calls = {"count": 0}
    sleeps: list[float] = []

    async def fake_sleep(delay: float):
        sleeps.append(delay)

    async def fake_create(**kwargs):
        calls["count"] += 1
        raise APITimeoutError(request=request)

    monkeypatch.setattr("app.llm.client.asyncio.sleep", fake_sleep)
    client._client = _stub_completion_client(fake_create)

    with pytest.raises(APITimeoutError):
        await client.chat(messages=[{"role": "user", "content": "hello"}], stream=False)

    assert calls["count"] == 3
    assert sleeps == [0.5, 1.0]


@pytest.mark.asyncio
async def test_chat_does_not_retry_non_transient_errors(monkeypatch):
    client = LLMClient(api_key="test", base_url="https://example.com/v1", model="demo")
    calls = {"count": 0}
    sleeps: list[float] = []

    async def fake_sleep(delay: float):
        sleeps.append(delay)

    async def fake_create(**kwargs):
        calls["count"] += 1
        raise RuntimeError("boom")

    monkeypatch.setattr("app.llm.client.asyncio.sleep", fake_sleep)
    client._client = _stub_completion_client(fake_create)

    with pytest.raises(RuntimeError, match="boom"):
        await client.chat(messages=[{"role": "user", "content": "hello"}], stream=False)

    assert calls["count"] == 1
    assert sleeps == []
