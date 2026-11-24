"""Görsel kataloğu — oda ve tesis fotoğraflarını ajana sunar, misafire gönderir."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from config import CONFIG

log = logging.getLogger("otel_demo.images")

_CATALOG_PATH = Path(__file__).resolve().parent / "image_catalog.json"
MAX_IMAGES = int(os.getenv("HOTEL_MAX_IMAGES", "3"))

_CATALOG: dict[str, dict] | None = None

SENT_MARKER_PREFIX = "[GORSEL_GONDERILDI:"


def format_sent_marker(keys: list[str]) -> str:
    return f"{SENT_MARKER_PREFIX} {','.join(k for k in keys if k)}]"


def parse_sent_marker(content: str) -> list[str]:
    c = (content or "").strip()
    if not c.startswith(SENT_MARKER_PREFIX):
        return []
    inner = c[len(SENT_MARKER_PREFIX):].rstrip("]").strip()
    return [k.strip() for k in inner.split(",") if k.strip()]


def _load() -> dict[str, dict]:
    global _CATALOG
    if _CATALOG is not None:
        return _CATALOG
    try:
        raw = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
        _CATALOG = raw.get("catalog", raw) if isinstance(raw, dict) else {}
    except Exception as e:
        log.warning("görsel kataloğu yüklenemedi: %s", e)
        _CATALOG = {}
    return _CATALOG


def valid_keys() -> list[str]:
    cat = _load()
    return [k for k, v in cat.items() if (v or {}).get("images")]


def label_for(key: str) -> str:
    return (_load().get(key) or {}).get("label", key)


def select(keys: list[str], max_total: int | None = None) -> list[dict]:
    cat = _load()
    cap = max_total or MAX_IMAGES
    seen_keys: list[str] = []
    for k in keys or []:
        if k in cat and (cat[k] or {}).get("images") and k not in seen_keys:
            seen_keys.append(k)
    if not seen_keys:
        return []

    pools = {k: list((cat[k] or {}).get("images") or []) for k in seen_keys}
    out: list[dict] = []
    used_urls: set[str] = set()
    while len(out) < cap and any(pools.values()):
        for k in seen_keys:
            if len(out) >= cap:
                break
            while pools[k]:
                url = pools[k].pop(0)
                if url and url not in used_urls:
                    used_urls.add(url)
                    out.append({"key": k, "label": cat[k].get("label", k), "url": url})
                    break
    return out


_ALL_KEYS = [
    "room_standard",
    "room_deluxe_sea",
    "room_family",
    "room_suite_jacuzzi",
    "room_engelsiz",
    "beach_pool",
    "spa_wellness",
    "dining",
    "exterior",
]

TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "send_images",
        "description": (
            f"Misafire {CONFIG.hotel_name} görseli (oda, plaj/havuz, restoran veya dış görünüm fotoğrafı) "
            "göndermek için kullan. Bir oda tipi ya da tesis alanı konuşmanın odağındaysa veya misafir "
            "açıkça fotoğraf/görsel isterse çağır. Tek seferde EN FAZLA 1-2 kategori seç. "
            "Key anlamları: "
            "room_standard=Standart Bahçe Manzaralı Oda, "
            "room_deluxe_sea=Deluxe Deniz & Kızkalesi Manzaralı Oda, "
            "room_family=Aile Odası (Ara Kapılı), "
            "room_suite_jacuzzi=Korykos Teras Suit (Jakuzili), "
            "room_engelsiz=Engelsiz / Erişilebilir Oda (yalnızca erişilebilirlik sorulursa), "
            "beach_pool=Kum Plaj & Açık Yüzme Havuzu, "
            "spa_wellness=Butik SPA, Hamam & Masaj, "
            "dining=Olba Teras Restoran & Kahvaltı, "
            "exterior=Otel Dış Görünüm & Bahçe."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "keys": {
                    "type": "array",
                    "description": "Gönderilecek görsel kategorileri (1-2 adet).",
                    "items": {"type": "string", "enum": _ALL_KEYS},
                }
            },
            "required": ["keys"],
        },
    },
}

