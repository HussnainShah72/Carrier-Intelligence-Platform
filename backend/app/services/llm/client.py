"""
Provider-agnostic LLM client.

Why a wrapper rather than one SDK?
----------------------------------
The interview module needs *streaming* so the first spoken sentence can start
before the full reply exists (an explicit assignment requirement).  Every
provider streams differently.  Isolating that here means the seven feature
modules call one small interface -- `complete()`, `stream()`, `complete_json()`
-- and the viva demo can switch provider with one line in `.env`.

Supported values for LLM_PROVIDER:
  anthropic | openai | gemini | groq | ollama | offline

`offline` is a deterministic, rule-based engine (see offline_engine.py).  It
exists so the product still demonstrates every screen without an API key, and
so the automated test suite is fully reproducible.  It is clearly reported as
degraded in /api/system/health and in the UI.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Iterator, Sequence

from app.core.config import settings
from app.core.errors import LLMError
from app.core.logging_setup import get_logger
from app.services.llm import json_guard

log = get_logger(__name__)


@dataclass(slots=True)
class LLMUsage:
    provider: str = ""
    model: str = ""
    prompt_chars: int = 0
    completion_chars: int = 0
    total_ms: float = 0.0
    ttft_ms: float | None = None
    degraded: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "prompt_chars": self.prompt_chars,
            "completion_chars": self.completion_chars,
            "total_ms": round(self.total_ms, 1),
            "ttft_ms": round(self.ttft_ms, 1) if self.ttft_ms is not None else None,
            "degraded": self.degraded,
        }


@dataclass(slots=True)
class LLMResponse:
    text: str
    usage: LLMUsage = field(default_factory=LLMUsage)


@dataclass(slots=True)
class StreamChunk:
    """One streamed delta, carrying the timing the performance report needs."""

    delta: str
    index: int
    elapsed_ms: float
    is_first: bool = False
    is_final: bool = False


class LLMClient:
    """Thin façade over whichever provider `.env` selects."""

    def __init__(
        self,
        provider: str | None = None,
        model: str | None = None,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> None:
        self.provider = (provider or settings.llm_provider).lower()
        self.model = model or (settings.default_model if self.provider == settings.llm_provider else "")
        self.temperature = settings.llm_temperature if temperature is None else temperature
        self.max_tokens = max_tokens or settings.llm_max_tokens
        self._client: Any = None
        # Set per call; used to pick an Anthropic effort level per task.
        self._current_task: str = "generic"

        if not self.model:
            self.model = {
                "anthropic": "claude-sonnet-5-5",
                "openai": "gpt-4o-mini",
                "gemini": "gemini-2.0-flash",
                "groq": "llama-3.3-70b-versatile",
                "ollama": "qwen2.5:3b-instruct",
                "offline": "offline-deterministic-v1",
            }.get(self.provider, "offline-deterministic-v1")

    # ------------------------------------------------------------------ info
    @property
    def is_offline(self) -> bool:
        return self.provider == "offline"

    def describe(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "streaming": self.provider != "offline",
            "degraded": self.is_offline,
            "temperature": self.temperature,
        }

    # -------------------------------------------------------------- complete
    def complete(
        self,
        prompt: str,
        *,
        system: str = "",
        temperature: float | None = None,
        max_tokens: int | None = None,
        task: str = "generic",
    ) -> LLMResponse:
        """Blocking completion.  Used everywhere except the interview turn."""
        self._current_task = task
        started = time.perf_counter()
        temp = self.temperature if temperature is None else temperature
        limit = max_tokens or self.max_tokens

        if self.is_offline:
            from app.services.llm.offline_engine import offline_complete

            text = offline_complete(task=task, prompt=prompt, system=system)
            usage = LLMUsage(
                provider="offline",
                model=self.model,
                prompt_chars=len(prompt),
                completion_chars=len(text),
                total_ms=(time.perf_counter() - started) * 1000,
                degraded=True,
            )
            return LLMResponse(text=text, usage=usage)

        try:
            text = self._provider_complete(prompt, system=system, temperature=temp, max_tokens=limit)
        except LLMError:
            raise
        except Exception as exc:  # provider SDK raised something of its own
            log.error("LLM call failed (%s/%s): %s", self.provider, self.model, exc)
            raise LLMError(self._explain_failure(exc)) from exc

        usage = LLMUsage(
            provider=self.provider,
            model=self.model,
            prompt_chars=len(prompt),
            completion_chars=len(text),
            total_ms=(time.perf_counter() - started) * 1000,
        )
        log.info("LLM %s/%s task=%s %.0fms %dch", self.provider, self.model, task, usage.total_ms, len(text))
        return LLMResponse(text=text, usage=usage)

    def complete_json(
        self,
        prompt: str,
        *,
        system: str = "",
        expect: type = dict,
        retries: int = 1,
        task: str = "generic",
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> tuple[Any, LLMUsage]:
        """
        Completion that must yield JSON.

        On a parse failure the model is re-asked once with an explicit
        correction instruction before the caller is told the call failed.
        """
        last_error: Exception | None = None
        attempt_prompt = prompt

        for attempt in range(retries + 1):
            response = self.complete(
                attempt_prompt,
                system=system,
                task=task,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            try:
                return json_guard.parse_json_payload(response.text, expect=expect), response.usage
            except Exception as exc:
                last_error = exc
                log.warning("JSON parse attempt %d/%d failed for task=%s", attempt + 1, retries + 1, task)
                attempt_prompt = (
                    f"{prompt}\n\n"
                    "IMPORTANT: your previous reply was not valid JSON. Reply with the JSON "
                    "object ONLY. No markdown fences, no commentary, no trailing commas."
                )

        assert last_error is not None
        raise last_error

    # ---------------------------------------------------------------- stream
    def stream(
        self,
        prompt: str,
        *,
        system: str = "",
        temperature: float | None = None,
        max_tokens: int | None = None,
        task: str = "generic",
    ) -> Iterator[StreamChunk]:
        """
        Yield deltas as they arrive.

        The interview pipeline consumes this, buffers to sentence boundaries,
        and sends each finished sentence to the local TTS engine immediately --
        that is what keeps end-of-speech-to-first-audio latency low.
        """
        self._current_task = task
        started = time.perf_counter()
        temp = self.temperature if temperature is None else temperature
        limit = max_tokens or self.max_tokens
        index = 0

        if self.is_offline:
            from app.services.llm.offline_engine import offline_complete

            text = offline_complete(task=task, prompt=prompt, system=system)
            for piece in _chunk_text(text):
                yield StreamChunk(
                    delta=piece,
                    index=index,
                    elapsed_ms=(time.perf_counter() - started) * 1000,
                    is_first=index == 0,
                )
                index += 1
            yield StreamChunk(delta="", index=index, elapsed_ms=(time.perf_counter() - started) * 1000, is_final=True)
            return

        try:
            for piece in self._provider_stream(prompt, system=system, temperature=temp, max_tokens=limit):
                if not piece:
                    continue
                yield StreamChunk(
                    delta=piece,
                    index=index,
                    elapsed_ms=(time.perf_counter() - started) * 1000,
                    is_first=index == 0,
                )
                index += 1
        except LLMError:
            raise
        except Exception as exc:
            log.error("LLM stream failed (%s/%s): %s", self.provider, self.model, exc)
            raise LLMError(self._explain_failure(exc, streaming=True)) from exc

        yield StreamChunk(delta="", index=index, elapsed_ms=(time.perf_counter() - started) * 1000, is_final=True)

    # -------------------------------------------------- provider adapters ---
    def _provider_complete(self, prompt: str, *, system: str, temperature: float, max_tokens: int) -> str:
        if self.provider == "anthropic":
            client = self._anthropic()
            kwargs = self._anthropic_kwargs(prompt, system=system, max_tokens=max_tokens,
                                            temperature=temperature)
            message = self._anthropic_call(client.messages.create, kwargs)
            return "".join(block.text for block in message.content if getattr(block, "type", "") == "text")

        if self.provider in ("openai", "groq", "ollama"):
            client = self._openai_compatible()
            kwargs = self._openai_kwargs(
                prompt, system=system, temperature=temperature, max_tokens=max_tokens
            )
            completion = self._openai_call(client.chat.completions.create, kwargs)
            return completion.choices[0].message.content or ""

        if self.provider == "gemini":
            client = self._gemini()
            from google.genai import types as genai_types  # type: ignore

            response = client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    system_instruction=system or None,
                    temperature=temperature,
                    max_output_tokens=max_tokens,
                ),
            )
            return response.text or ""

        raise LLMError(f"Unknown LLM provider '{self.provider}'. Check LLM_PROVIDER in .env.")

    def _provider_stream(
        self, prompt: str, *, system: str, temperature: float, max_tokens: int
    ) -> Iterator[str]:
        if self.provider == "anthropic":
            client = self._anthropic()
            kwargs = self._anthropic_kwargs(prompt, system=system, max_tokens=max_tokens,
                                            temperature=temperature)
            manager = self._anthropic_call(client.messages.stream, kwargs)
            with manager as stream:
                for delta in stream.text_stream:
                    yield delta
            return

        if self.provider in ("openai", "groq", "ollama"):
            client = self._openai_compatible()
            kwargs = self._openai_kwargs(
                prompt, system=system, temperature=temperature, max_tokens=max_tokens
            )
            kwargs["stream"] = True
            stream = self._openai_call(client.chat.completions.create, kwargs)
            for event in stream:
                if not event.choices:
                    continue
                delta = event.choices[0].delta
                if delta and delta.content:
                    yield delta.content
            return

        if self.provider == "gemini":
            client = self._gemini()
            from google.genai import types as genai_types  # type: ignore

            stream = client.models.generate_content_stream(
                model=self.model,
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    system_instruction=system or None,
                    temperature=temperature,
                    max_output_tokens=max_tokens,
                ),
            )
            for event in stream:
                if event.text:
                    yield event.text
            return

        raise LLMError(f"Unknown LLM provider '{self.provider}'.")

    # --------------------------------- OpenAI-compatible parameter handling
    #
    # Groq's current chat models are the `gpt-oss` family, which are REASONING
    # models: they emit reasoning tokens before any visible content, and those
    # tokens count against `max_tokens`. Measured on Groq, an unconstrained
    # reply spent ~187 reasoning tokens before writing a word, so a request with
    # a small `max_tokens` returns finish_reason="length" and EMPTY content.
    #
    # Two consequences handled here:
    #   1. `reasoning_effort="low"` cuts reasoning by roughly 93% (187 -> 13
    #      tokens measured) and is also the fastest, which matters because the
    #      interview turn sits on the measured reply-latency path.
    #   2. `max_tokens` is given a floor so reasoning cannot consume the whole
    #      budget and leave nothing for the answer.

    _REASONING_EFFORT_BY_TASK = {
        "interview_turn": "low",   # latency-critical
        "cv_parse": "low",         # schema-following extraction
        "posting_skills": "low",
        "probe": "low",
        "role_skills": "medium",
        "gap_advice": "medium",
        "bullet_improve": "medium",
        "interview_plan": "medium",
        "scoring": "medium",
    }

    # Headroom so reasoning tokens cannot starve the visible answer.
    MIN_REASONING_MAX_TOKENS = 512

    def _openai_kwargs(
        self, prompt: str, *, system: str, temperature: float, max_tokens: int
    ) -> dict[str, Any]:
        messages = ([{"role": "system", "content": system}] if system else []) + [
            {"role": "user", "content": prompt}
        ]
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if self._emits_reasoning_tokens():
            kwargs["max_tokens"] = max(max_tokens, self.MIN_REASONING_MAX_TOKENS)
            effort = self._REASONING_EFFORT_BY_TASK.get(self._current_task, "low")
            kwargs["reasoning_effort"] = effort
        return kwargs

    def _emits_reasoning_tokens(self) -> bool:
        """Whether the configured model spends tokens reasoning before replying."""
        model = self.model.lower()
        return self.provider == "groq" and any(
            marker in model for marker in ("gpt-oss", "qwen3", "deepseek-r1", "reasoning")
        )

    def _openai_call(self, method: Any, kwargs: dict[str, Any]) -> Any:
        """Invoke the method, dropping `reasoning_effort` if the model rejects it."""
        try:
            return method(**kwargs)
        except Exception as exc:
            if "reasoning_effort" not in kwargs:
                raise
            text = str(exc).lower()
            if "reasoning_effort" not in text and "unrecognized" not in text and "unknown" not in text:
                raise
            log.info(
                "%s rejected reasoning_effort for %s; retrying without it",
                self.provider, self.model,
            )
            retry = dict(kwargs)
            retry.pop("reasoning_effort", None)
            return method(**retry)

    def _explain_failure(self, exc: Exception, *, streaming: bool = False) -> str:
        """
        Turn a provider SDK exception into something the user can act on.

        Rate limiting and unknown model ids are by far the most common failures
        when a free API tier is configured, and the raw SDK message does not
        tell a user what to do about either.
        """
        text = str(exc).lower()
        status = getattr(exc, "status_code", None)

        if status == 429 or "rate limit" in text or "rate_limit" in text:
            return (
                f"{self.provider} rate-limited this request even after retrying. "
                "Free tiers cap tokens per minute, and one interview turn costs roughly "
                "2,800 tokens. Wait a minute and try again, choose a smaller model, or "
                "switch LLM_PROVIDER to 'ollama' for an unlimited local model."
            )
        if status in (401, 403) or "invalid api key" in text or "authentication" in text:
            return (
                f"{self.provider} rejected the API key. Check the key for that provider in "
                "backend/.env, and that LLM_PROVIDER matches the key you set."
            )
        if status == 404 or "does not exist" in text or "model_not_found" in text or "decommissioned" in text:
            return (
                f"The model '{self.model}' is not available on {self.provider}. Model ids "
                "change: list the current ones and set LLM_MODEL in backend/.env. For Groq: "
                "curl -H \"Authorization: Bearer $GROQ_API_KEY\" "
                "https://api.groq.com/openai/v1/models"
            )
        if "timeout" in text or "timed out" in text:
            return (
                "The language model did not respond in time. Try again, or use a smaller "
                "model for faster replies."
            )
        if streaming:
            return "The language model stream was interrupted. Please try the turn again."
        return (
            "The language model could not be reached. Check your API key and network, "
            "or switch LLM_PROVIDER to 'offline' in the backend .env file."
        )

    # ------------------------------------- Anthropic parameter compatibility
    #
    # The current Claude API (anthropic-version 2026-10-21, which the installed
    # SDK sends by default) REMOVED the sampling parameters: a request carrying
    # `temperature`, `top_p` or `top_k` is rejected with a 400 on every model.
    # Response depth is controlled by `output_config.effort` instead.
    #
    # So the Anthropic path must not send `temperature` at all. The project's
    # per-task temperature is translated into an effort level, and because the
    # user can configure any model string in .env -- including an older model
    # that predates `output_config` -- an unexpected 400 about either parameter
    # is caught once and the request retried without it.

    _EFFORT_BY_TASK = {
        # Latency-critical: this one sits on the measured reply-latency path.
        "interview_turn": "low",
        # Schema-following extraction; depth adds cost without adding accuracy.
        "cv_parse": "low",
        "posting_skills": "low",
        "probe": "low",
        # Judgement tasks, where a little more deliberation is worth paying for.
        "role_skills": "medium",
        "gap_advice": "medium",
        "bullet_improve": "medium",
        "interview_plan": "medium",
        "scoring": "medium",
    }

    def _anthropic_kwargs(
        self, prompt: str, *, system: str, max_tokens: int, temperature: float
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system or "You are a helpful assistant.",
            "messages": [{"role": "user", "content": prompt}],
        }
        effort = self._EFFORT_BY_TASK.get(self._current_task)
        if effort is None:
            # Fall back to the caller's temperature as a coarse proxy for how
            # much deliberation the task wants.
            effort = "low" if temperature <= 0.3 else "medium"
        kwargs["output_config"] = {"effort": effort}
        return kwargs

    def _anthropic_call(self, method: Any, kwargs: dict[str, Any]) -> Any:
        """
        Invoke an Anthropic SDK method, dropping parameters the model rejects.

        A model configured in .env may be newer or older than this code expects,
        so rather than hard-code a compatibility matrix, an unsupported-parameter
        400 is detected once and the parameter removed.
        """
        try:
            return method(**kwargs)
        except Exception as exc:
            message = str(exc).lower()
            unsupported = [key for key in ("output_config", "effort", "temperature")
                           if key in message and key in str(kwargs)]
            if not unsupported or "output_config" not in kwargs:
                raise
            log.info(
                "Anthropic rejected output_config for model %s (%s); retrying without it",
                self.model, message[:140],
            )
            retry = dict(kwargs)
            retry.pop("output_config", None)
            return method(**retry)

    # ------------------------------------------------------- SDK construction
    def _anthropic(self):
        if self._client is None:
            if not settings.anthropic_api_key:
                raise LLMError("ANTHROPIC_API_KEY is not set in the backend .env file.")
            try:
                import anthropic  # type: ignore
            except ImportError as exc:
                raise LLMError("The 'anthropic' package is not installed.") from exc
            self._client = anthropic.Anthropic(
                api_key=settings.anthropic_api_key, timeout=settings.llm_timeout_seconds
            )
        return self._client

    def _openai_compatible(self):
        """OpenAI, Groq and Ollama all speak the OpenAI chat-completions API."""
        if self._client is None:
            try:
                from openai import OpenAI  # type: ignore
            except ImportError as exc:
                raise LLMError("The 'openai' package is not installed.") from exc

            # The SDK retries 429 and 5xx with exponential backoff and honours
            # Retry-After. The default of 2 is too low for a free tier whose
            # token-per-minute budget a single interview turn can consume.
            retries = settings.llm_max_retries

            if self.provider == "openai":
                if not settings.openai_api_key:
                    raise LLMError("OPENAI_API_KEY is not set in the backend .env file.")
                self._client = OpenAI(
                    api_key=settings.openai_api_key,
                    timeout=settings.llm_timeout_seconds,
                    max_retries=retries,
                )
            elif self.provider == "groq":
                if not settings.groq_api_key:
                    raise LLMError("GROQ_API_KEY is not set in the backend .env file.")
                self._client = OpenAI(
                    api_key=settings.groq_api_key,
                    base_url="https://api.groq.com/openai/v1",
                    timeout=settings.llm_timeout_seconds,
                    max_retries=retries,
                )
            else:  # ollama -- local server, no key required
                self._client = OpenAI(
                    api_key="ollama",
                    base_url=f"{settings.ollama_base_url.rstrip('/')}/v1",
                    timeout=settings.llm_timeout_seconds,
                    max_retries=retries,
                )
        return self._client

    def _gemini(self):
        if self._client is None:
            if not settings.gemini_api_key:
                raise LLMError("GEMINI_API_KEY is not set in the backend .env file.")
            try:
                from google import genai  # type: ignore
            except ImportError as exc:
                raise LLMError("The 'google-genai' package is not installed.") from exc
            self._client = genai.Client(api_key=settings.gemini_api_key)
        return self._client


def _chunk_text(text: str, size: int = 24) -> Iterator[str]:
    """Split text into word-aligned pieces so offline mode also 'streams'."""
    words = text.split(" ")
    buffer = ""
    for word in words:
        buffer = f"{buffer} {word}".strip() if buffer else word
        if len(buffer) >= size:
            yield buffer + " "
            buffer = ""
    if buffer:
        yield buffer


# ---------------------------------------------------------------------------
# Shared singleton
# ---------------------------------------------------------------------------

_default_client: LLMClient | None = None


def get_llm() -> LLMClient:
    global _default_client
    if _default_client is None:
        _default_client = LLMClient()
        log.info("LLM client ready: %s", _default_client.describe())
    return _default_client


def reset_llm() -> None:
    """Drop the cached client (used after a settings change, and by tests)."""
    global _default_client
    _default_client = None


def probe_llm() -> dict[str, Any]:
    """Health check used by the Settings page: does the configured LLM answer?"""
    client = get_llm()
    info = client.describe()
    if client.is_offline:
        info.update(
            {
                "reachable": True,
                "detail": "Deterministic offline engine (no API key configured). "
                "Set LLM_PROVIDER and the matching API key in backend/.env for full quality.",
            }
        )
        return info

    started = time.perf_counter()
    try:
        response = client.complete(
            "Reply with exactly: OK",
            system="You are a connectivity probe. Reply with exactly the requested text.",
            # Reasoning models spend tokens before writing content, so a
            # tiny budget here returns an empty reply and looks like a fault.
            max_tokens=256,
            temperature=0.0,
            task="probe",
        )
        info.update(
            {
                "reachable": True,
                "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                "detail": response.text.strip()[:60] or "empty reply",
            }
        )
    except Exception as exc:
        info.update(
            {
                "reachable": False,
                "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                "detail": str(exc)[:200],
            }
        )
    return info


def summarise_usages(usages: Sequence[LLMUsage]) -> dict[str, Any]:
    total = sum(u.total_ms for u in usages)
    return {
        "calls": len(usages),
        "total_ms": round(total, 1),
        "providers": sorted({u.provider for u in usages if u.provider}),
        "models": sorted({u.model for u in usages if u.model}),
        "degraded": any(u.degraded for u in usages),
    }
