"""Otel bilgi tabanı — yerel JSON dosyaları + kategori yönlendirme."""

from __future__ import annotations

import json
from pathlib import Path

from config import CONFIG

_DATA_DIR = Path(__file__).resolve().parent / "knowledge_data"

_FILES = {
    "overview_policies": "overview_and_policies.json",
    "rooms_facilities": "rooms_and_facilities.json",
    "pools_spa_kids": "pools_spa_kids.json",
    "meetings_events": "meetings_events.json",
    "location_transport": "location_transport.json",
    "dining": "dining__yeme_icme_canli_muzik.json",
    "transport_bus": "ulasim.json",
}

_CACHE: dict[str, str] = {}


def _load() -> None:
    if _CACHE:
        return
    for cat, fn in _FILES.items():
        p = _DATA_DIR / fn
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            _CACHE[cat] = json.dumps(data, ensure_ascii=False)
        except Exception:
            _CACHE[cat] = "{}"


def get_hotel_info(category: str) -> str:
    """Bir kategori için ham bilgi JSON'unu (string) döndürür."""
    _load()
    return _CACHE.get(category, f"Bilinmeyen kategori: {category}. Geçerli: {', '.join(_FILES)}")


ROUTING_HINT = (
    "Kategoriler ve örnek anahtarlar:\n"
    "- dining: kahvaltı, akşam yemeği, restoran, Olba Teras, bar, plaj bar, içecek, alkol, "
    "canlı müzik, cuma cumartesi müzik, balayı ikramı, doğum günü pastası, yarım pansiyon, oda+kahvaltı.\n"
    "- pools_spa_kids: plaj, deniz, Kızkalesi plajı, şezlong, şemsiye, açık havuz, çocuk havuzu, "
    "günübirlik kullanım (day use), günübirlik havuz/plaj ücreti, SPA, hamam, sauna, masaj, kese-köpük, "
    "bone, çocuk oyun alanı.\n"
    "- rooms_facilities: oda tipleri (Standart, Deluxe Deniz Manzaralı, Aile Odası, Korykos Teras Suit, "
    "Engelsiz Oda), jakuzi, balkon, manzara, kapasite, tekne turu, dalış, kano, aktivite, temizlik.\n"
    "- meetings_events: toplantı salonu, Kilikiya salonu, seminer, butik düğün, nişan, grup konaklama.\n"
    "- location_transport: konum, adres, Kızkalesi, Erdemli, Mersin, Adana, Çukurova Havalimanı (COV), "
    "VIP transfer, transfer ücreti, Cennet-Cehennem, Narlıkuyu mesafeleri.\n"
    "- transport_bus: dolmuş, minibüs, HAVAŞ, Mersin otogar veya Silifke'den toplu taşıma ile geliş.\n"
    "- overview_policies: genel bilgi, check-in/check-out saatleri, evcil hayvan (pet), otopark, "
    "elektrikli araç şarjı, Wi-Fi, iptal politikası, kredi kartı taksit, evlilik cüzdanı şartı var mı, iletişim.\n"
    "\nÇAKIŞMA: Birden çok kategori uyuyorsa EN SPESİFİK alanı seç."
)

TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_hotel_info",
        "description": (
            f"{CONFIG.hotel_name} hakkında bilgi (oda, plaj/havuz/spa, yeme-içme, toplantı, konum, "
            "politika, ulaşım) almak için kullan. " + ROUTING_HINT
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": list(_FILES.keys()),
                    "description": "Bilgi kategorisi.",
                }
            },
            "required": ["category"],
        },
    },
}

