"""Medya sınıflandırma (D3) — bir mesaj düz metin mi, ses mi, görsel mi?"""

from __future__ import annotations

import logging
import os
import re

import requests

from config import CONFIG

log = logging.getLogger("otel_demo.media")
_VERIFY_SSL = os.getenv("HOTELRUNNER_VERIFY_SSL", "1") != "0"

_AUDIO_HOST_PATTERNS = (
    "lookaside.fbsbx.com",
    "lookaside.instagram.com",
    "scontent.cdninstagram.com",
    "manybot",
    "fbsbx",
    "fbcdn.net",
    ".mp4", ".m4a", ".ogg", ".opus", ".wav", ".mp3",
)
_IMAGE_EXT_RE = re.compile(r"\.(jpg|jpeg|png|webp|gif|heic)(\?|$)", re.I)
_URL_RE = re.compile(r"^https?://", re.I)
_UA = "Mozilla/5.0 (compatible; KorykosBot/2.0; +https://www.korykoshotel.com)"
_FALLBACK_STATUSES = {403, 405, 501}


def _is_url(text: str) -> bool:
    return bool(text) and isinstance(text, str) and bool(_URL_RE.match(text.strip()))


def _is_image_url(text: str) -> bool:
    if not _is_url(text):
        return False
    return _IMAGE_EXT_RE.search(text.strip()) is not None


def _is_audio_url(text: str) -> bool:
    if not _is_url(text):
        return False
    lower = text.strip().lower()
    has_pattern = any(p in lower for p in _AUDIO_HOST_PATTERNS)
    return has_pattern and not _is_image_url(text)


def _probe_content_type(url: str) -> str | None:
    timeout = CONFIG.media_probe_timeout
    _hdr = {"User-Agent": _UA}
    try:
        resp = requests.head(url, timeout=timeout, allow_redirects=False, headers=_hdr, verify=_VERIFY_SSL)
    except Exception:
        resp = None

    if resp is None or resp.status_code in _FALLBACK_STATUSES:
        try:
            resp = requests.get(
                url,
                timeout=timeout,
                allow_redirects=False,
                headers={**_hdr, "Range": "bytes=0-0"},
                stream=True,
                verify=_VERIFY_SSL,
            )
            resp.close()
        except Exception:
            return None

    if 300 <= resp.status_code < 400:
        return None

    ct_raw = resp.headers.get("content-type", "") or ""
    ct = ct_raw.split(";")[0].strip().lower()
    return ct or None


def classify_media_url(text: str) -> str:
    if not _is_url(text):
        return "text"
    trimmed = text.strip()
    ct = _probe_content_type(trimmed)
    if ct:
        if ct.startswith("audio/"):
            return "audio"
        if ct.startswith("image/") or ct.startswith("video/"):
            return "image"
    if _is_image_url(trimmed):
        return "image"
    if _is_audio_url(trimmed):
        return "audio"
    return "text"

