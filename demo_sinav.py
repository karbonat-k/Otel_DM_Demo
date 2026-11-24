"""Otel_DM_Demo — 20 Senaryoluk Kapsamlı Doğrulama Sınavı (4 Dil + Fiyat + Fotoğraf + Telegram Devir).

Bu betik botu 20 gerçekçi misafir sorusuyla uçtan uca test eder:
- Türkçe, İngilizce, Rusça ve Almanca sorular
- Fiyat ve müsaitlik hesaplama (Oda+Kahvaltı ve Yarım Pansiyon)
- 12+ yaş çocuk kuralı
- Dolu tarihte (15-16 Ağustos) otomatik alternatif tarih önerme
- Eksik bilgide (tarih veya çocuk yaşı yokken) fiyat uydurmama
- Oda ve plaj fotoğrafı gönderme
- Şikâyet ve canlı destek talebinde Telegram üzerinden personele devir (escalation)
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import agent
from decisions import contains_price_mention

SCENARIOS = [
    {
        "id": "S01_GENEL_KONUM",
        "title": "Konum ve Denize Mesafe (TR)",
        "msg": "Merhaba, oteliniz tam olarak nerede ve denize sıfır mı? Plajınız kum mu?",
        "check": lambda r: any(k in r["text"].lower() for k in ("kızkalesi", "mersin", "sıfır", "kum")),
    },
    {
        "id": "S02_FIYAT_2YETISKIN",
        "title": "2 Yetişkin 2 Gece Fiyat Sorgusu (TR)",
        "msg": "18-20 Haziran için 2 yetişkin oda fiyatlarınız nedir?",
        "check": lambda r: contains_price_mention(r["text"]) and bool(r.get("link")),
    },
    {
        "id": "S03_EKSIK_COCUK_YASI",
        "title": "Çocuk Yaşı Eksikken Fiyat Uydurmama (TR)",
        "msg": "10-12 Temmuz arası 2 yetişkin ve 2 çocuk geleceğiz, fiyat nedir?",
        "check": lambda r: ("yaş" in r["text"].lower()) and not contains_price_mention(r["text"]),
    },
    {
        "id": "S04_12YAS_USTU_KURALI",
        "title": "12+ Yaş Çocuk Yetişkin Sınıflaması (TR)",
        "msg": "20-22 Haziran 2 yetişkin ve 14 yaşında 1 çocuğumuz var, fiyat alabilir miyim?",
        "check": lambda r: contains_price_mention(r["text"]) and ("yetişkin" in r["text"].lower() or "3" in r["text"]),
    },
    {
        "id": "S05_DOLU_TARIH_ALTERNATIF",
        "title": "Dolu Tarihte (15-16 Ağustos) Otomatik Alternatif Önerme (TR)",
        "msg": "15-16 Ağustos 2 yetişkin için müsait odanız var mı, fiyat nedir?",
        "check": lambda r: contains_price_mention(r["text"]) and any(k in r["text"].lower() for k in ("müsait", "alternatif", "16", "14")),
    },
    {
        "id": "S06_ODA_FOTOGRAFI_JAKUZI",
        "title": "Jakuzili Suit Bilgisi ve Fotoğraf Gönderimi (TR)",
        "msg": "Jakuzili odanız var mı? Fotoğraflarını görebilir miyim?",
        "check": lambda r: ("teras suit" in r["text"].lower() or "jakuzi" in r["text"].lower()) and ("room_suite_jacuzzi" in (r.get("image_keys") or [])),
    },
    {
        "id": "S07_KAHVALTI_VE_YARIM_PANSIYON",
        "title": "Kahvaltı Saatleri ve Akşam Yemeği Konsepti (TR)",
        "msg": "Kahvaltı saat kaçta başlıyor ve yarım pansiyon seçersek akşam yemeğinde neler var?",
        "check": lambda r: ("08:00" in r["text"] or "8" in r["text"]) and ("11:00" in r["text"] or "akşam" in r["text"].lower()),
    },
    {
        "id": "S08_EVCIL_HAYVAN",
        "title": "Evcil Hayvan Politikası (TR)",
        "msg": "5 kiloluk küçük bir köpeğimiz var, otele kabul ediyor musunuz?",
        "check": lambda r: ("350" in r["text"] or "bahçe" in r["text"].lower() or "kabul" in r["text"].lower()),
    },
    {
        "id": "S09_HAVALIMANI_TRANSFER",
        "title": "Çukurova Havalimanı VIP Transfer (TR)",
        "msg": "Çukurova Havalimanı'ndan otele transfer hizmetiniz var mı, ücreti ne kadar?",
        "check": lambda r: ("2.800" in r["text"] or "2800" in r["text"]) and ("vito" in r["text"].lower() or "transfer" in r["text"].lower()),
    },
    {
        "id": "S10_GUNUBIRLIK_PLAJ_HAVUZ",
        "title": "Günübirlik Havuz ve Plaj Kullanımı (TR)",
        "msg": "Otelde konaklamadan sadece günübirlik havuz ve plajınızı kullanabilir miyiz? Ücreti nedir?",
        "check": lambda r: "950" in r["text"],
    },
    {
        "id": "S11_EVLILIK_CUZDANI",
        "title": "Çift Konaklamasında Evlilik Cüzdanı Sorusu (TR)",
        "msg": "Kız arkadaşımla hafta sonu gelmek istiyoruz, evlilik cüzdanı şartınız var mı?",
        "check": lambda r: any(k in r["text"].lower() for k in ("hayır", "yok", "bulunmamaktadır", "şartı yok")),
    },
    {
        "id": "S12_KURBAN_BAYRAMI",
        "title": "Resmi/Dini Tatil Tarihini Bulup Fiyatlama (TR)",
        "msg": "Kurban Bayramı'nda 2 yetişkin için gecelik veya toplam fiyatlarınız ne kadar?",
        "check": lambda r: ("mayıs" in r["text"].lower() or contains_price_mention(r["text"])),
    },
    {
        "id": "S13_IPTAL_VE_TAKSIT",
        "title": "İptal Koşulları ve Kredi Kartına Taksit (TR)",
        "msg": "Rezervasyonu iptal etmek istersek kesinti olur mu? Kredi kartına taksit yapıyor musunuz?",
        "check": lambda r: ("7 gün" in r["text"].lower() or "iade" in r["text"].lower()) and ("taksit" in r["text"].lower() or "3" in r["text"]),
    },
    {
        "id": "S14_BALAYI_VE_CANLI_MUZIK",
        "title": "Balayı İkramı ve Canlı Müzik (TR)",
        "msg": "Balayı için gelmeyi düşünüyoruz, bir sürpriziniz oluyor mu? Bir de akşamları canlı müzik var mı?",
        "check": lambda r: ("cuma" in r["text"].lower() or "cumartesi" in r["text"].lower() or "müzik" in r["text"].lower()),
    },
    {
        "id": "S15_SIKAYET_TELEGRAM_DEVIR",
        "title": "Acil Oda Şikâyeti -> Telegram Personel Devri (TR)",
        "msg": "Şu an 204 numaralı odada kalıyorum, klima bozuldu ve oda çok sıcak! Resepsiyona ulaşamıyorum, acil birini gönderin!",
        "check": lambda r: bool(r.get("escalated")),
    },
    {
        "id": "S16_CANLI_DESTEK_DEVIR",
        "title": "Telefon Bırakıp Aranma Talebi -> Telegram Devri (TR)",
        "msg": "Ben yetkili biriyle telefonda görüşüp rezervasyonumu öyle kesinleştirmek istiyorum. Numaram 0532 111 22 33, beni arar mısınız?",
        "check": lambda r: bool(r.get("escalated")),
    },
    {
        "id": "S17_ENGLISH_PRICE_AND_BEACH",
        "title": "İngilizce Fiyat ve Plaj Sorusu (EN)",
        "msg": "Hello! Do you have a available sea view room for 2 adults from June 18 to June 20? And is the beach sandy?",
        "check": lambda r: contains_price_mention(r["text"]) and any(w in r["text"].lower() for w in ("beach", "room", "breakfast", "sea", "june")),
    },
    {
        "id": "S18_RUSSIAN_FAMILY_INFO",
        "title": "Rusça Aile Odası ve Havuz Sorusu (RU)",
        "msg": "Здравствуйте! У вас есть семейный номер для 2 взрослых и 2 детей (5 и 8 лет) с 10 по 13 июня? Сколько стоит?",
        "check": lambda r: contains_price_mention(r["text"]) and bool(any(ch in r["text"] for ch in "абвгдеёжзийклмнопрстуфхцчшщъыьэюя")),
    },
    {
        "id": "S19_GERMAN_TRANSFER_AND_PETS",
        "title": "Almanca Havalimanı Transfer ve Evcil Hayvan Sorusu (DE)",
        "msg": "Guten Tag, bieten Sie einen Flughafentransfer vom Flughafen Çukurova an und sind kleine Hunde im Hotel erlaubt?",
        "check": lambda r: any(w in r["text"].lower() for w in ("transfer", "hund", "ja", "tl", "flughafen")),
    },
    {
        "id": "S20_COK_TUR_HAFIZA",
        "title": "Çok Turlu Konuşma Hafızası Testi (TR)",
        "multi_turn": [
            "Merhaba, 22-24 Eylül için 2 yetişkin fiyat bakıyorum.",
            "Peki bu söylediğiniz fiyatlara akşam yemeği dahil mi, yoksa sadece kahvaltı mı?",
        ],
        "check": lambda r: any(w in r["text"].lower() for w in ("kahvaltı", "yarım pansiyon", "akşam yemeği")),
    },
]


def main() -> int:
    print("=" * 76)
    print("🧪 Otel_DM_Demo — 20 Senaryoluk Otomatik Kalite ve Çoklu Dil Sınavı")
    print("=" * 76)

    passed = 0
    results_log = []
    start_all = time.monotonic()

    for idx, sc in enumerate(SCENARIOS, 1):
        t0 = time.monotonic()
        history: list[dict] = []
        if "multi_turn" in sc:
            res = {}
            for turn_msg in sc["multi_turn"]:
                res = agent.respond(turn_msg, history=history, user_id=f"test_{sc['id']}", platform="Instagram")
                history.append({"role": "user", "content": turn_msg})
                history.append({"role": "assistant", "content": res.get("text", "")})
        else:
            res = agent.respond(sc["msg"], history=[], user_id=f"test_{sc['id']}", platform="Instagram")

        dt = round(time.monotonic() - t0, 2)
        ok = False
        try:
            ok = bool(sc["check"](res))
        except Exception as e:
            res["check_error"] = str(e)

        if ok:
            passed += 1
        badge = "✅ GEÇTİ" if ok else "❌ KALDI"
        print(f"\n[{idx:02d}/20] {badge} | {sc['id']} — {sc['title']} ({dt} sn)")
        if "multi_turn" in sc:
            print(f"   👤 Misafir (Tur 2): {sc['multi_turn'][-1]}")
        else:
            print(f"   👤 Misafir: {sc['msg']}")
        print(f"   🤖 Bot: {res.get('text', '')}")
        if res.get("images"):
            print(f"   📸 Görseller: {res.get('image_keys')}")
        if res.get("escalated"):
            print(f"   🔔 Telegram Devir: {res.get('escalation_info')}")

        results_log.append({
            "id": sc["id"],
            "title": sc["title"],
            "passed": ok,
            "duration_s": dt,
            "response": res,
        })

    total_time = round(time.monotonic() - start_all, 1)
    print("\n" + "=" * 76)
    print(f"📊 SONUÇ: {passed} / {len(SCENARIOS)} senaryo başarıyla geçti ({total_time} sn)")
    print("=" * 76)

    out_path = Path(__file__).resolve().parent / "sinav_sonucu.json"
    out_path.write_text(
        json.dumps({"passed": passed, "total": len(SCENARIOS), "results": results_log}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return 0 if passed == len(SCENARIOS) else 1


if __name__ == "__main__":
    sys.exit(main())

