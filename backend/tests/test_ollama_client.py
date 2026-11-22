"""
Ollama-specific behaviour of the LLM client (no Ollama server needed).

Regression tests for two problems found in QA:
  * the OpenAI-compatible /v1 endpoint ignores `num_ctx`, so prompts were cut
    to Ollama's default 2,048-token window from the front;
  * a stopped Ollama cost ~40 s per call (SDK retries) while health said "ok".
"""

from __future__ import annotations

import json
import time

import httpx


def test_ollama_requests_use_native_api_with_context_window(monkeypatch) -> None:
    from app.core.config import settings
    from app.services.llm.client import LLMClient

    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"message": {"content": "OK"}, "done": True})

    client = LLMClient(provider="ollama", model="qwen2.5:3b-instruct-q4_K_M")
    client._ollama_http = httpx.Client(base_url="http://ollama.test", transport=httpx.MockTransport(handler))

    assert client.complete("ping", system="sys").text == "OK"
    assert seen["path"] == "/api/chat"
    assert seen["body"]["options"]["num_ctx"] == settings.ollama_num_ctx >= 8192
    assert seen["body"]["messages"][0] == {"role": "system", "content": "sys"}


def test_ollama_streaming_parses_ndjson() -> None:
    from app.services.llm.client import LLMClient

    lines = [
        {"message": {"content": "Hello"}, "done": False},
        {"message": {"content": " there."}, "done": False},
        {"message": {"content": ""}, "done": True},
    ]
    body = "\n".join(json.dumps(line) for line in lines).encode()
    client = LLMClient(provider="ollama", model="llama3.2:3b")
    client._ollama_http = httpx.Client(
        base_url="http://ollama.test",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=body)),
    )

    text = "".join(chunk.delta for chunk in client.stream("hi") if chunk.delta)
    assert text == "Hello there."


def test_stopped_ollama_is_reported_quickly(monkeypatch) -> None:
    from app.core.config import settings
    from app.services.llm import client as client_mod

    monkeypatch.setattr(settings, "llm_provider", "ollama")
    monkeypatch.setattr(settings, "ollama_base_url", "http://127.0.0.1:9")  # nothing listens here

    started = time.perf_counter()
    status = client_mod.check_ollama(max_age_seconds=0)
    assert status["reachable"] is False
    assert "not reachable" in status["detail"]
    # Windows retries a refused connect for a few seconds; the old behaviour was ~40 s.
    assert time.perf_counter() - started < 15
