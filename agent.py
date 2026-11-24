"""Ana ajan — Korykos Boutique Hotel & Beach (Mersin Kızkalesi) müşteri temsilcisi.

Araçlar:
1. get_hotel_info   — Otel bilgi tabanı (oda, plaj/havuz/spa, restoran, konum/transfer, politikalar)
2. get_holiday      — TR resmi ve dini tatil tarihleri
3. get_price        — Konaklama müsaitlik ve fiyat hesaplama + dolu tarihte alternatif önerme
4. send_images      — Oda ve tesis fotoğrafları gönderme
5. escalate_to_human — Canlı otel personeline / resepsiyona Telegram üzerinden anlık devir

Model: OpenAI gpt-4.1-mini.
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import escalation
import holidays
import hotelrunner
import images
import knowledge
import llm
from config import CONFIG
from decisions import (
    GROUP_MSG,
    HEADCOUNT_MISMATCH_MSG,
    PRICE_NOT_GROUNDED_FALLBACK,
    alternative_windows as _alternative_windows,
    contains_price_mention as _contains_price_mention,
    headcount_mismatch as _headcount_mismatch,
    reclassify_ages as _reclassify_ages,
    spa_context_without_room as _spa_context_without_room,
    validate_booking as _validate_booking,
    wants_accessible as _wants_accessible,
)

log = logging.getLogger("otel_demo.agent")
MAX_TURNS = 5

FALLBACK_TEXT = (
    f"Bu konu hakkında elimde net bilgi bulunmuyor. Kesin yanıt için {CONFIG.hotel_phone} "
    f"numaralı hattımızdan bize ulaşabilir veya {CONFIG.hotel_email} adresine yazabilirsiniz."
)


def _today_tr() -> str:
    try:
        return datetime.now(ZoneInfo("Europe/Istanbul")).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return datetime.now().strftime("%Y-%m-%d %H:%M")


_TR_HINTS = {
    "ve", "bir", "için", "icin", "mı", "mi", "mu", "mü", "var", "yok", "oda",
    "fiyat", "fiyatı", "fiyati", "gece", "kişi", "kisi", "çocuk", "cocuk",
    "merhaba", "selam", "kaç", "kac", "ne", "nedir", "müsait", "musait", "tarih",
    "istiyorum", "yaş", "yas", "günü", "gunu", "kişilik", "kisilik",
}
_EN_HINTS = {
    "the", "do", "you", "have", "is", "are", "room", "rooms", "price", "prices",
    "night", "nights", "available", "availability", "hello", "hi", "can", "for",
    "what", "how", "much", "we", "want", "would", "like", "weekend", "adults",
    "children", "please", "thanks", "thank", "book", "booking", "your", "any",
}
_DE_HINTS = {
    "hallo", "guten", "zimmer", "preis", "preise", "nacht", "nächte", "personen",
    "kinder", "frei", "verfügbar", "bitte", "danke", "wir", "möchten", "strand", "frühstück",
}


def _detect_foreign_lang(text: str) -> str | None:
    """Mesaj net olarak İngilizce, Rusça veya Almanca ise dil adını döndürür; Türkçe ise None."""
    t = (text or "").strip()
    if not t:
        return None
    # Kiril alfabesi -> Rusça
    if re.search(r"[А-Яа-яЁё]", t):
        return "Russian (Русский)"
    low = t.lower()
    if any(ch in low for ch in "çğışİ"):
        return None
    words = set(re.findall(r"[a-zäöüß']+", low))
    if words & _TR_HINTS:
        return None
    if len(words & _DE_HINTS) >= 2:
        return "German (Deutsch)"
    if len(words & _EN_HINTS) >= 2:
        return "English"
    return None


SYSTEM_TEMPLATE = """Rolün
- Mersin Kızkalesi'nde denize sıfır konumda yer alan "{hotel_name}" otelinin dijital misafir ilişkileri temsilcisisin.
- Misafirle sıcak, nazik, güven veren, KISA ve ÖZ konuşursun.

Genel kurallar
- Misafirin yazdığı DİLDE cevap ver (Türkçe -> Türkçe, İngilizce -> İngilizce, Rusça -> Rusça, Almanca -> Almanca, Arapça -> Arapça).
  Bu kural ZORUNLUDUR: misafir yabancı bir dilde yazdıysa cevabının TAMAMI o dilde olsun. Araç çıktıları (otel bilgisi, fiyat özeti) Türkçe gelse bile cevabını misafirin diline çevirerek aktar.
- Düz metin yaz. Kalın/markdown (**...**) KULLANMA. Tablo, kod bloğu, başlık (#) kullanma.
- Cevaplar kısa, net ve kolay okunur olsun (2-5 kısa cümle).
- "bugün", "yarın", "bu hafta sonu", "3 gece", "ayın 20'si" gibi ifadeleri bugüne göre gerçek YYYY-MM-DD tarihine çevir.
- SAYI = TARİH DEĞİL: Kişi sayısı, çocuk yaşı veya oda sayısı bağlamındaki sayılar tarih değildir.
- KIRMIZI KURAL: Otel hakkındaki HİÇBİR soruyu (kahvaltı, plaj, havuz, odalar, jakuzi, evcil hayvan, transfer, konum, iptal şartı vb.) `get_hotel_info` aracını çağırmadan cevaplama. Tahmin yapma, bilgi uydurma.
- Bir konuda bilgi bulamazsan: "{fallback}" de.

Canlı Personele Devir (`escalate_to_human` aracı)
- Şu durumlarda MUTLAKA `escalate_to_human` aracını çağır:
  1) Misafir açıkça bir insanla / yetkiliyle / resepsiyonla konuşmak isterse veya telefon numarasını bırakıp "beni arayın" derse (`category="canli_destek"` veya `"rezervasyon_onay"`),
  2) Misafir konaklama sırasında veya öncesinde bir ŞİKÂYET, öfke, mağduriyet veya oda arızası (klima çalışmıyor, oda temizlenmedi, gürültü var vb.) bildirirse (`category="sikayet"`, `urgency="acil"`),
  3) Misafir standart dışı özel indirim pazarlığı, 20+ kişilik grup/düğün/toplantı teklifi veya özel organizasyon talep ederse (`category="ozel_talep"` veya `"grup_etkinlik"`).
- `escalate_to_human` çağırdığında misafire talebinin ve iletişim bilgisinin anında otel yetkilisine iletildiğini, ekibin en kısa sürede kendisiyle ilgileneceğini nazikçe belirt. Normal sorularda (bu araç çağrılmadığında) ise asla sahte "sizi arayacağız" sözü verme.

Görsel Gönderme (`send_images` aracı)
- Misafir fotoğraf/görsel/resim isterse VEYA konuşma belirli bir oda tipine (Standart, Deluxe Deniz Manzaralı, Aile Odası, Korykos Teras Suit) ya da tesis alanına (plaj/havuz, restoran, spa) odaklandıysa `send_images` aracını 1-2 uygun kategoriyle çağır.
- Genel fiyat listesi sayarken tüm odaların fotoğrafını yığma; tarih, ulaşım veya politika sorularında görsel gönderme.
- Aynı konuşmada daha önce gönderdiğin görsel kategorisini tekrar gönderme.

Akış A — Rezervasyon / Müsaitlik / Konaklama Fiyatı (`get_price` aracı)
- Zorunlu bilgiler: giriş tarihi, çıkış tarihi, yetişkin sayısı, çocuk varsa çocuk sayısı ve çocuk yaşları.
- TARİH ARALIĞI = GİRİŞ -> ÇIKIŞ: Misafirin söylediği son gün ÇIKIŞ günüdür ("24 25 Haziran" -> 24 giriş, 25 çıkış, 1 gece; "10-14 Temmuz" -> 10 giriş, 14 çıkış, 4 gece). Gece sayısı verilirse çıkış = giriş + gece sayısı.
- Çocuk varsa yaşlarını MUTLAKA öğren. Otelimizde 0-6 yaş ilk çocuk ücretsiz, 7-11 yaş çocuk indirimli, 12 yaş ve üzeri yetişkin sayılır.
- Eksik bilgi varsa (ör. tarih yok, kişi sayısı yok veya çocuk yaşı söylenmemiş) `get_price` ÇAĞIRMA; önce eksik bilgiyi kısaca sor.
- Misafir bir bayram/tatil adı söylerse (Kurban Bayramı, Ramazan Bayramı, 29 Ekim vb.) önce `get_holiday` ile tarih aralığını öğren, sonra `get_price` çağır.
- `get_price` sonucunda hem "Oda + Kahvaltı" hem "Yarım Pansiyon (kahvaltı + akşam yemeği)" fiyatları döner; misafir tek bir konsept belirtmediyse her iki seçeneği de net olarak sun.
- Verdiğin her fiyat o odanın tüm geceler ve tüm misafirler dahil TOPLAM konaklama ücretidir (kişi başı değildir).
- İstenen tarih doluysa (`available: false`), araç otomatik olarak yakın alternatif tarihleri dener ve `alternatifler` alanında döndürür; misafire önce istediği tarihin dolu olduğunu söyleyip doğrulanan alternatif tarihi somut fiyatıyla öner.
- Kesin rezervasyon oluşturmak isteyen misafire `get_price`'tan dönen online rezervasyon bağlantısını paylaş veya {hotel_phone} numaralı hattımızı / aranma talebini öner.

Akış B — Otel Hakkında Genel Bilgi (`get_hotel_info` aracı)
- Oda tipleri, jakuzi (yalnızca Korykos Teras Suit'te vardır), denize sıfır kum plaj, günübirlik havuz/plaj kullanımı, evcil hayvan kuralı, Çukurova Havalimanı VIP transfer, kahvaltı/restoran ve iptal politikası sorularında ilgili kategoriyle `get_hotel_info` çağır ve yalnızca oradaki bilgiye dayan.
"""

PRICE_TOOL = {
    "type": "function",
    "function": {
        "name": "get_price",
        "description": (
            "Belirli tarihler ve misafir sayısı için müsaitlik + konaklama fiyatını öğrenmek. "
            "Tüm zorunlu bilgiler (giriş, çıkış, yetişkin/çocuk, çocuk yaşları) netse çağır."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "checkin_date": {"type": "string", "description": "Giriş tarihi YYYY-MM-DD"},
                "checkout_date": {"type": "string", "description": "Çıkış tarihi YYYY-MM-DD"},
                "rooms": {
                    "type": "array",
                    "description": "Oda başına misafir listesi. Tek oda ise tek elemanlı dizi.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "adult_count": {"type": "integer"},
                            "child_count": {"type": "integer"},
                            "child_ages": {"type": "array", "items": {"type": "integer"}},
                        },
                        "required": ["adult_count"],
                    },
                },
            },
            "required": ["checkin_date", "checkout_date", "rooms"],
        },
    },
}

TOOLS = [
    knowledge.TOOL_SCHEMA,
    holidays.TOOL_SCHEMA,
    PRICE_TOOL,
    images.TOOL_SCHEMA,
    escalation.TOOL_SCHEMA,
]

MAX_ALTERNATIVE_PROBES = 3
ALTERNATIVE_TIME_BUDGET_S = 5.0


def _probe_alternatives(
    checkin: str,
    checkout: str,
    rooms: list[dict],
    include_accessible: bool,
    state: dict,
) -> list[dict]:
    adaylar = _alternative_windows(checkin, checkout, today=_today_tr(), limit=MAX_ALTERNATIVE_PROBES)
    bulunan: list[dict] = []
    baslangic = time.monotonic()
    for alt_ci, alt_co in adaylar:
        if time.monotonic() - baslangic > ALTERNATIVE_TIME_BUDGET_S:
            break
        try:
            alt = hotelrunner.quote(alt_ci, alt_co, rooms, include_accessible=include_accessible)
        except hotelrunner.HotelRunnerError:
            continue
        if not alt.get("available"):
            continue
        state["price_grounded"] = True
        bulunan.append({
            "checkin": alt_ci,
            "checkout": alt_co,
            "summary": alt.get("message"),
            "link": alt.get("link"),
        })
        break
    return bulunan


def _multi_family_quote(
    checkin: str,
    checkout: str,
    rooms: list[dict],
    state: dict,
    include_accessible: bool = False,
) -> str:
    ci, co = hotelrunner._shift_past_dates(checkin, checkout)
    norm = hotelrunner._norm_rooms(rooms)
    nights = hotelrunner._day_count(ci, co)
    lines = []
    any_ok = False
    for fam in norm:
        label = hotelrunner._guest_summary([fam])
        try:
            res = hotelrunner.quote(ci, co, [fam], include_accessible=include_accessible)
        except hotelrunner.HotelRunnerError:
            lines.append(f"- {label}: fiyatı şu an getiremedim.")
            continue
        opts = res.get("rooms") or []
        if not res.get("available") or not opts:
            lines.append(f"- {label}: bu tarihlerde müsait oda bulunmuyor.")
            continue
        any_ok = True
        best = min(opts, key=lambda x: x["total"])
        boards = best.get("boards") or [{"meal_plan": best.get("meal_plan"), "total": best["total"]}]
        priced = ", ".join(
            f"{(b.get('meal_plan') or 'fiyat').lower()} {hotelrunner.format_try(b['total'])}"
            for b in boards
        )
        lines.append(f"- {label}, {best['name']}: {priced} ({nights} gece toplam)")
    if any_ok:
        state["price_grounded"] = True
    link = hotelrunner.booking_link(ci, co, norm)
    state["link"] = link
    head = f"{hotelrunner._fmt_date(ci)} - {hotelrunner._fmt_date(co)} ({nights} gece) için aile/oda başına en uygun fiyatlar:"
    return json.dumps(
        {"available": any_ok, "summary": head + "\n" + "\n".join(lines), "link": link},
        ensure_ascii=False,
    )


def _dispatch(name: str, args: dict, state: dict) -> str:
    try:
        if name == "get_hotel_info":
            state["info_grounded"] = True
            return knowledge.get_hotel_info(args.get("category", ""))

        if name == "get_holiday":
            return holidays.get_holiday(args.get("name", ""))

        if name == "escalate_to_human":
            res = escalation.notify_staff(
                category=args.get("category", "canli_destek"),
                urgency=args.get("urgency", "normal"),
                summary=args.get("summary", ""),
                guest_contact=args.get("guest_contact", "Belirtilmedi"),
                user_id=state.get("user_id", "demo_misafir"),
                platform=state.get("platform", "Instagram"),
                last_user_message=state.get("current_user_text", ""),
            )
            state["escalated"] = True
            state["escalation_info"] = res
            return json.dumps(
                {
                    "status": "escalated",
                    "telegram_notified": res.get("sent", False),
                    "not": (
                        "Talep otel yetkilisine Telegram üzerinden anında iletildi. "
                        "Misafire talebinin ilgili ekibe aktarıldığını ve en kısa sürede "
                        "kendisiyle ilgilenileceğini nazikçe bildir."
                    ),
                },
                ensure_ascii=False,
            )

        if name == "send_images":
            keys = args.get("keys") or []
            if isinstance(keys, str):
                keys = [keys]
            if state.get("drop_rooms_for_spa"):
                keys = [k for k in keys if not str(k).startswith("room_")]
            already = {img["url"] for img in state.get("images", [])}
            sent_before = state.get("sent_before") or set()
            picked = [
                img
                for img in images.select(keys)
                if img["url"] not in already and img["key"] not in sent_before
            ]
            if not picked:
                return (
                    "Bu kategori için yeni gönderilecek görsel yok (daha önce paylaşıldı). "
                    "Aynı fotoğrafı tekrar gönderme; metinle yardımcı ol."
                )
            state.setdefault("images", []).extend(picked)
            labels = sorted({img["label"] for img in picked})
            return json.dumps(
                {
                    "status": "queued",
                    "count": len(picked),
                    "areas": labels,
                    "not": (
                        f"Görsel(ler) cevabınla birlikte misafire gidecek ({', '.join(labels)}). "
                        "Cevap metninde fotoğrafları paylaştığını kısaca belirt."
                    ),
                },
                ensure_ascii=False,
            )

        if name == "get_price":
            rooms = args.get("rooms") or [{"adult_count": 2, "child_count": 0, "child_ages": []}]
            if _headcount_mismatch(state.get("current_user_text", ""), rooms):
                return json.dumps({"available": None, "summary": HEADCOUNT_MISMATCH_MSG}, ensure_ascii=False)
            promoted_ages = sorted(
                a
                for r in (rooms or [])
                for a in (r.get("child_ages") or [])
                if isinstance(a, int) and a >= 12
            )
            rooms = _reclassify_ages(rooms)
            ci, co = args.get("checkin_date", ""), args.get("checkout_date", "")
            include_accessible = bool(state.get("include_accessible"))
            err = _validate_booking(ci, co, rooms)
            if err:
                return json.dumps({"available": None, "summary": err}, ensure_ascii=False)
            if len(rooms) > 1:
                return _multi_family_quote(ci, co, rooms, state, include_accessible)
            try:
                res = hotelrunner.quote(ci, co, rooms, include_accessible=include_accessible)
            except hotelrunner.HotelRunnerError as e:
                log.warning("get_price quote hata: %s", e)
                link = hotelrunner.booking_link(
                    *hotelrunner._shift_past_dates(ci, co),
                    hotelrunner._norm_rooms(rooms),
                )
                state["link"] = link
                return json.dumps(
                    {
                        "available": None,
                        "summary": "Anlık fiyatı şu an getiremedim; güncel fiyat ve müsaitliği rezervasyon bağlantısından görebilirsiniz.",
                        "link": link,
                    },
                    ensure_ascii=False,
                )
            if res.get("link"):
                state["link"] = res["link"]
            if res.get("available"):
                state["price_grounded"] = True
            payload: dict = {
                "available": res.get("available"),
                "summary": res.get("message"),
                "link": res.get("link"),
            }
            codes = {
                b.get("meal_plan_code")
                for r in (res.get("rooms") or [])
                for b in (r.get("boards") or [])
                if b.get("meal_plan_code")
            }
            if len(codes) > 1:
                payload["not"] = (
                    "Bu tarihler için hem Oda+Kahvaltı hem Yarım Pansiyon seçeneği mevcut. "
                    "Misafir özel bir konsept seçmediyse cevabında her iki konseptin fiyatını da birlikte sun."
                )
            if promoted_ages:
                toplam_yetiskin = sum(int(r.get("adult_count") or 0) for r in rooms)
                yas_metni = " ve ".join(str(a) for a in promoted_ages)
                payload["yas_siniflamasi"] = (
                    f"{yas_metni} yaşındaki misafir(ler) otel kuralı gereği YETİŞKİN sayıldı; "
                    f"fiyat toplam {toplam_yetiskin} yetişkin üzerinden hesaplandı."
                )
                payload["not"] = (
                    f"Bu fiyatta {yas_metni} yaşındaki misafir(ler) otel kuralı gereği YETİŞKİN "
                    f"sayıldı (11 yaş ve altı çocuk, 12 ve üzeri yetişkin). Cevabında bunu kısaca belirt."
                )
            if not res.get("available"):
                alternatifler = _probe_alternatives(ci, co, rooms, include_accessible, state)
                if alternatifler:
                    payload["alternatifler"] = alternatifler
                    payload["not"] = (
                        "İstenen tarih müsait DEĞİL. Ancak aşağıdaki alternatif tarih(ler) şu an MÜSAİT. "
                        "Cevabında önce istenen tarihin dolu olduğunu söyle, ardından bu alternatif "
                        "tarihi ve fiyatını öner."
                    )
                else:
                    payload["not"] = (
                        f"İstenen tarih ve yakın tarihler dolu. Dolu olduğunu dürüstçe söyle ve "
                        f"kesin durum için {CONFIG.hotel_phone} numaralı hattımıza yönlendir."
                    )
            return json.dumps(payload, ensure_ascii=False)
    except Exception as e:
        log.warning("tool %s hata: %s", name, e)
        return f"Araç hatası: {e}"
    return f"Bilinmeyen araç: {name}"


def respond(
    user_message: str,
    history: list[dict] | None = None,
    user_id: str = "demo_misafir",
    platform: str = "Instagram",
) -> dict:
    """Misafir mesajına cevap üretir.

    Dönüş:
      {
        "text": <cevap>,
        "link": <rezervasyon linki | None>,
        "images": [<url>, ...],
        "image_keys": [<key>, ...],
        "escalated": <bool>,
        "escalation_info": <dict | None>
      }
    """
    system_content = SYSTEM_TEMPLATE.format(
        hotel_name=CONFIG.hotel_name,
        hotel_phone=CONFIG.hotel_phone,
        fallback=FALLBACK_TEXT,
    )
    foreign_lang = _detect_foreign_lang(user_message)
    if foreign_lang:
        system_content += (
            f"\n\nÖNEMLİ DİL KURALI: Misafir {foreign_lang} dilinde yazıyor. "
            f"Bu yanıtın TAMAMINI {foreign_lang} dilinde yaz. Araç çıktıları Türkçe gelse bile "
            f"(oda adı, fiyat özeti, tesis bilgisi) tamamını {foreign_lang} diline çevir."
        )
    system_content += f"\n\nBugünün tarihi ve saati (Europe/Istanbul): {_today_tr()}"
    messages = [{"role": "system", "content": system_content}]

    sent_before: set[str] = set()
    for m in (history or []):
        content = m.get("content") or ""
        if m.get("role") == "system" and content.strip().startswith(images.SENT_MARKER_PREFIX):
            sent_before.update(images.parse_sent_marker(content))
            continue
        messages.append(m)
    messages.append({"role": "user", "content": user_message})

    guest_text = " ".join(str(m.get("content") or "") for m in messages if m.get("role") == "user")
    state: dict = {
        "user_id": user_id,
        "platform": platform,
        "link": None,
        "images": [],
        "escalated": False,
        "escalation_info": None,
        "include_accessible": _wants_accessible(guest_text),
        "current_user_text": user_message,
        "sent_before": sent_before,
        "drop_rooms_for_spa": _spa_context_without_room(user_message),
        "price_grounded": False,
        "info_grounded": False,
    }

    for turn_idx in range(MAX_TURNS):
        msg = llm.chat(messages, tools=TOOLS)
        tool_calls = getattr(msg, "tool_calls", None)
        if not tool_calls:
            text = (msg.content or "").strip()
            if _contains_price_mention(text) and not state.get("price_grounded") and not state.get("info_grounded"):
                if turn_idx < MAX_TURNS - 1:
                    log.warning("fiyat iddiası doğrulanmamış -> yeniden dene")
                    messages.append({
                        "role": "system",
                        "content": (
                            "UYARI: Son cevabın bir TL tutarı içeriyordu ama bu turda o tutarı "
                            "doğrulayan bir araç (get_price veya get_hotel_info) hiç çağrılmadı. "
                            "Fiyat uydurma; ilgili aracı ŞİMDİ çağır."
                        ),
                    })
                    continue
                text = PRICE_NOT_GROUNDED_FALLBACK
            return {
                "text": text,
                "link": state["link"],
                "images": [img["url"] for img in state["images"]],
                "image_keys": list(dict.fromkeys(img["key"] for img in state["images"])),
                "escalated": state["escalated"],
                "escalation_info": state["escalation_info"],
            }

        messages.append({
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in tool_calls
            ],
        })
        for tc in tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            result = _dispatch(tc.function.name, args, state)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "name": tc.function.name,
                "content": result,
            })

    msg = llm.chat(messages, tools=None)
    text = (msg.content or "").strip()
    if _contains_price_mention(text) and not state.get("price_grounded") and not state.get("info_grounded"):
        text = PRICE_NOT_GROUNDED_FALLBACK
    return {
        "text": text,
        "link": state["link"],
        "images": [img["url"] for img in state["images"]],
        "image_keys": list(dict.fromkeys(img["key"] for img in state["images"])),
        "escalated": state["escalated"],
        "escalation_info": state["escalation_info"],
    }

