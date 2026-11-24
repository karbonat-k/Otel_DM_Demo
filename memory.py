"""Konuşma hafızası — Supabase tanımlıysa PostgREST üzerinden, değilse yerel bellek (in-memory) üzerinden.

Demo ve yerel testlerde Supabase gerekmeden son N mesajı bellekte tutar; Supabase eklendiğinde
otomatik olarak kalıcı veritabanına geçer.
"""

from __future__ import annotations

import logging
import os

import requests

from config import CONFIG

log = logging.getLogger("otel_demo.memory")
_VERIFY_SSL = os.getenv("HOTELRUNNER_VERIFY_SSL", "1") != "0"
_TIMEOUT = 10
_TABLE = "otel_demo_chat_memory"

# Yerel (in-memory) yedek hafıza: user_id -> [{role, content}, ...]
_LOCAL_STORE: dict[str, list[dict]] = {}


def _supabase_ready() -> bool:
    return bool(CONFIG.supabase_url and CONFIG.supabase_service_key)


def _headers() -> dict:
    k = CONFIG.supabase_service_key
    return {"apikey": k, "Authorization": f"Bearer {k}", "Content-Type": "application/json"}


def load(user_id: str, limit: int | None = None) -> list[dict]:
    """Son N mesajı kronolojik (eski -> yeni) sırada döndürür."""
    n = limit or CONFIG.history_window
    if _supabase_ready():
        url = f"{CONFIG.supabase_url}/rest/v1/{_TABLE}"
        params = {
            "user_id": f"eq.{user_id}",
            "select": "role,content",
            "order": "created_at.desc",
            "limit": str(n),
        }
        try:
            r = requests.get(url, headers=_headers(), params=params, timeout=_TIMEOUT, verify=_VERIFY_SSL)
            r.raise_for_status()
            rows = r.json()
            return [{"role": x["role"], "content": x["content"]} for x in reversed(rows)]
        except Exception as e:
            log.warning("supabase memory load failed (%s), yerel belleğe düşülüyor: %s", user_id, e)

    rows = _LOCAL_STORE.get(user_id, [])
    return list(rows[-n:])


def save(user_id: str, platform: str, role: str, content: str) -> None:
    """Tek mesaj ekler."""
    if not content:
        return
    bucket = _LOCAL_STORE.setdefault(user_id, [])
    bucket.append({"role": role, "content": content})
    if len(bucket) > 50:
        del bucket[:-50]

    if _supabase_ready():
        url = f"{CONFIG.supabase_url}/rest/v1/{_TABLE}"
        body = {"user_id": user_id, "platform": platform, "role": role, "content": content}
        try:
            h = {**_headers(), "Prefer": "return=minimal"}
            requests.post(url, headers=h, json=body, timeout=_TIMEOUT, verify=_VERIFY_SSL)
        except Exception as e:
            log.warning("supabase memory save failed (%s): %s", user_id, e)


def clear(user_id: str) -> None:
    """Kullanıcının yerel konuşma geçmişini sıfırlar (demo sıfırlama için)."""
    _LOCAL_STORE.pop(user_id, None)

