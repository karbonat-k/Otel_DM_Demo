"""LLM sarmalayıcı: sohbet (OpenAI tool-calling) + ses transkripsiyon (OpenAI gpt-4o-mini-transcribe).

Tek sağlayıcı: OpenAI (`OPENAI_API_KEY`).
- Ana ajan: `gpt-4.1-mini`
- Ses çevirisi: `gpt-4o-mini-transcribe` (gerekirse `whisper-1` fallback)
"""

from __future__ import annotations

import io
import logging
import os
import re

import httpx
from openai import OpenAI

from config import CONFIG

log = logging.getLogger("otel_demo.llm")

_VERIFY_SSL = os.getenv("HOTELRUNNER_VERIFY_SSL", "1") != "0"
_PROMPT_CACHE_KEY = "korykos-demo-v1"


def _openai_client() -> OpenAI:
    if not CONFIG.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY tanımlı değil (_knowledge/credentials/master.env)")
    return OpenAI(
        api_key=CONFIG.openai_api_key,
        max_retries=1,
        http_client=httpx.Client(verify=_VERIFY_SSL, timeout=30.0),
    )


def _sampling_kilitli(model: str) -> bool:
    return bool(re.match(r"^gpt-5\.6", model or "", re.IGNORECASE))


def chat(
    messages: list[dict],
    tools: list[dict] | None = None,
    model: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 1500,
    tool_choice: str = "auto",
    top_p: float = 0.9,
    frequency_penalty: float = 0.2,
):
    """OpenAI chat completion (ana ajan). tool_calls için ham message nesnesini döndürür."""
    secilen = model or CONFIG.agent_model
    kw: dict = {"model": secilen, "messages": messages}
    if _sampling_kilitli(secilen):
        kw["max_completion_tokens"] = max_tokens
        kw["reasoning_effort"] = "none"
    else:
        kw["temperature"] = temperature
        kw["max_tokens"] = max_tokens
        kw["top_p"] = top_p
        kw["frequency_penalty"] = frequency_penalty
    if tools:
        kw["tools"] = tools
        kw["tool_choice"] = tool_choice
    kw["extra_body"] = {"prompt_cache_key": _PROMPT_CACHE_KEY}
    resp = _openai_client().chat.completions.create(**kw)
    _log_usage(secilen, resp)
    return resp.choices[0].message


def _log_usage(model: str, resp) -> None:
    u = getattr(resp, "usage", None)
    if not u:
        return
    girdi = getattr(u, "prompt_tokens", 0) or 0
    cikti = getattr(u, "completion_tokens", 0) or 0
    detay = getattr(u, "prompt_tokens_details", None)
    cached = (getattr(detay, "cached_tokens", 0) or 0) if detay else 0
    oran = round(100 * cached / girdi) if girdi else 0
    log.info("[llm_usage] model=%s input=%s cached=%s (%%%s) output=%s",
             model, girdi, cached, oran, cikti)


def transcribe(audio_bytes: bytes, filename: str = "audio.ogg", language: str | None = None) -> str:
    """Ses -> metin (OpenAI gpt-4o-mini-transcribe, hata olursa whisper-1 fallback)."""
    client = _openai_client()
    bio = io.BytesIO(audio_bytes)
    bio.name = filename
    kwargs: dict = {"file": bio, "model": CONFIG.transcribe_model}
    if language:
        kwargs["language"] = language
    try:
        r = client.audio.transcriptions.create(**kwargs)
        return (getattr(r, "text", "") or "").strip()
    except Exception as e:
        log.warning("transcribe (%s) hata, whisper-1 deneniyor: %s", CONFIG.transcribe_model, e)
        bio.seek(0)
        kwargs["model"] = "whisper-1"
        r = client.audio.transcriptions.create(**kwargs)
        return (getattr(r, "text", "") or "").strip()

