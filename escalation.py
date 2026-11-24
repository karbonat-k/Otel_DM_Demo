"""Personel devir (Escalation) modülü — Telegram üzerinden otel yetkilisine anlık bildirim.

Bot aşağıdaki durumlarda `escalate_to_human` aracını çağırır:
1. Misafir açıkça canlı bir yetkili / resepsiyon / insanla görüşmek istediğinde
2. Ciddi şikâyet, memnuniyetsizlik veya acil oda sorunu bildirdiğinde
3. Özel fiyat pazarlığı, grup/etkinlik teklifi veya botun yetkisini aşan özel talep olduğunda
4. Misafir kesin rezervasyon onayı / ödeme adımı için aranmak istediğinde
"""

from __future__ import annotations

import json
import logging
import os

import requests
import urllib3

from config import CONFIG

log = logging.getLogger("otel_demo.escalation")
_VERIFY_SSL = os.getenv("HOTELRUNNER_VERIFY_SSL", "1") != "0"
if not _VERIFY_SSL:
    urllib3.disable_warnings()
_TIMEOUT = 10

TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "escalate_to_human",
        "description": (
            "Konuşmayı canlı otel yetkilisine / resepsiyona devretmek ve Telegram üzerinden "
            "ekibe anlık bildirim göndermek için kullan. NE ZAMAN ÇAĞRILIR: "
            "(1) Misafir açıkça bir insanla / yetkiliyle / resepsiyonla görüşmek isterse veya "
            "telefon numarasını bırakıp aranmak isterse; "
            "(2) Şikâyet, öfke, mağduriyet veya odada acil teknik sorun (klima, su, temizlik vb.) varsa; "
            "(3) Özel indirim pazarlığı, 20+ kişilik grup/düğün/toplantı teklifi veya botun bilgi "
            "tabanında olmayan kritik bir talep varsa. "
            "Sıradan fiyat, müsaitlik veya genel bilgi sorularında ÇAĞIRMA."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": ["sikayet", "canli_destek", "rezervasyon_onay", "ozel_talep", "grup_etkinlik"],
                    "description": "Devir sebebi kategorisi.",
                },
                "urgency": {
                    "type": "string",
                    "enum": ["normal", "yuksek", "acil"],
                    "description": "Öncelik seviyesi (şikâyet ve oda içi arızalarda 'acil').",
                },
                "summary": {
                    "type": "string",
                    "description": "Otel personelinin tek bakışta anlayacağı 1-2 cümlelik Türkçe özet.",
                },
                "guest_contact": {
                    "type": "string",
                    "description": "Misafirin paylaştığı telefon, isim veya oda numarası (yoksa 'Belirtilmedi').",
                },
            },
            "required": ["category", "urgency", "summary"],
        },
    },
}

_CATEGORY_LABELS = {
    "sikayet": "🚨 Şikâyet / Memnuniyetsizlik",
    "canli_destek": "👤 Canlı Yetkili Talebi",
    "rezervasyon_onay": "🛎️ Rezervasyon / Aranma Talebi",
    "ozel_talep": "✨ Özel Talep / İndirim",
    "grup_etkinlik": "👥 Grup / Etkinlik Talebi",
}

_URGENCY_BADGES = {
    "acil": "🔴 ACİL",
    "yuksek": "🟠 YÜKSEK",
    "normal": "🔵 NORMAL",
}


def notify_staff(
    category: str,
    urgency: str,
    summary: str,
    guest_contact: str = "Belirtilmedi",
    user_id: str = "demo_misafir",
    platform: str = "Instagram",
    last_user_message: str = "",
) -> dict:
    """Telegram üzerinden otel yetkilisine bildirim gönderir ve sonucu döndürür."""
    cat_label = _CATEGORY_LABELS.get(category, category)
    urg_label = _URGENCY_BADGES.get(urgency, urgency)
    contact = (guest_contact or "Belirtilmedi").strip()

    text = (
        f"🔔 PERSONEL DEVRİ ({urg_label})\n"
        f"🏨 {CONFIG.hotel_name}\n\n"
        f"📂 Kategori: {cat_label}\n"
        f"📱 Kanal: {platform} (Kullanıcı: {user_id})\n"
        f"📞 İletişim / Bilgi: {contact}\n"
        f"📝 Özet: {summary}\n"
    )
    if last_user_message:
        trimmed = last_user_message[:300]
        text += f"\n💬 Son Mesaj:\n\"{trimmed}\""

    if CONFIG.dry_run:
        log.info("[DRY_RUN] Telegram bildirimi: %s", summary)
        return {"sent": True, "mode": "dry_run", "summary": summary}

    if not CONFIG.telegram_bot_token or not CONFIG.admin_chat_id:
        log.warning("Telegram token veya ADMIN_CHAT_ID eksik; bildirim yalnızca loglandı.")
        return {"sent": False, "reason": "missing_telegram_config", "summary": summary}

    url = f"https://api.telegram.org/bot{CONFIG.telegram_bot_token}/sendMessage"
    try:
        r = requests.post(
            url,
            json={"chat_id": CONFIG.admin_chat_id, "text": text},
            timeout=_TIMEOUT,
            verify=_VERIFY_SSL,
        )
        ok = r.status_code == 200 and r.json().get("ok") is True
        if ok:
            log.info("Telegram personel bildirimi gönderildi (category=%s urgency=%s)", category, urgency)
        else:
            log.warning("Telegram bildirim hatası: %s %s", r.status_code, r.text[:200])
        return {"sent": bool(ok), "category": category, "urgency": urgency, "summary": summary}
    except Exception as e:
        log.warning("Telegram bağlantı hatası: %s", e)
        return {"sent": False, "error": str(e), "summary": summary}
