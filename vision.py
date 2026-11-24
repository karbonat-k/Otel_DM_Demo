"""Görsel betimleme (D2) — misafirin gönderdiği görseli kısa Türkçe metne çevirir."""

from __future__ import annotations

import base64
import logging
import os

import httpx

from config import CONFIG

log = logging.getLogger("otel_demo.vision")
_VERIFY_SSL = os.getenv("HOTELRUNNER_VERIFY_SSL", "1") != "0"

_DOWNLOAD_TIMEOUT = 8.0
_API_TIMEOUT = 30.0
_API_URL = "https://api.openai.com/v1/chat/completions"
_UA = "Mozilla/5.0 (compatible; KorykosBot/2.0; +https://www.korykoshotel.com)"

_ALLOWED_MODELS = {"gpt-4o-mini", "gpt-4.1-mini"}
_DEFAULT_MODEL = "gpt-4o-mini"

VISION_SYSTEM = (
    f"Sen {CONFIG.hotel_name} müşteri temsilcisisin. Misafirin gönderdiği görseli kısa Türkçe "
    "açıklayacaksın. Amaç: bir sonraki cevabı üretirken konuyu bilmek. Spekülasyon yapma, "
    "görselde net ne varsa söyle. 2-4 cümle yeterli."
)


def _download_as_data_uri(url: str) -> str | None:
    max_bytes = CONFIG.vision_max_mb * 1024 * 1024
    try:
        with httpx.Client(
            timeout=_DOWNLOAD_TIMEOUT,
            verify=_VERIFY_SSL,
            follow_redirects=True,
            headers={"User-Agent": _UA},
        ) as client:
            res = client.get(url)
            res.raise_for_status()
            ct = (res.headers.get("content-type", "") or "").split(";")[0].strip().lower()
            if not ct.startswith("image/"):
                log.warning("[vision] beklenmeyen content-type: %s", ct or "yok")
                return None
            buf = res.content
            if len(buf) > max_bytes:
                log.warning("[vision] görsel çok büyük: %d bayt", len(buf))
                return None
            b64 = base64.b64encode(buf).decode("ascii")
            return f"data:{ct};base64,{b64}"
    except Exception as e:
        log.warning("[vision] indirme hatası: %s", e)
        return None


def describe_image(image_url: str, user_hint: str = "") -> str | None:
    if not CONFIG.openai_api_key:
        log.warning("[vision] OPENAI_API_KEY yok — görsel betimlenemiyor")
        return None

    data_uri = _download_as_data_uri(image_url)
    if not data_uri:
        return None

    user_text = (
        f'Misafir şu metni de yazdı: "{user_hint}". Bunu görseli yorumlarken dikkate al.'
        if user_hint and len(user_hint) > 1
        else "Misafir sadece görseli gönderdi, başka metin yok."
    )

    model = CONFIG.vision_model if CONFIG.vision_model in _ALLOWED_MODELS else _DEFAULT_MODEL
    try:
        with httpx.Client(timeout=_API_TIMEOUT, verify=_VERIFY_SSL) as client:
            resp = client.post(
                _API_URL,
                headers={
                    "Authorization": f"Bearer {CONFIG.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": 400,
                    "messages": [
                        {"role": "system", "content": VISION_SYSTEM},
                        {
                            "role": "user",
                            "content": [
                                {"type": "image_url", "image_url": {"url": data_uri}},
                                {"type": "text", "text": user_text},
                            ],
                        },
                    ],
                },
            )
            resp.raise_for_status()
            data = resp.json()
            text = (data.get("choices", [{}])[0].get("message", {}).get("content", "") or "").strip()
            return text or None
    except Exception as e:
        log.warning("[vision] API çağrı hatası: %s", e)
        return None

