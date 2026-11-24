"""Korykos Boutique Hotel & Beach — Demo Fiyat ve Müsaitlik Motoru (hotelrunner.py uyumlu arayüz).

Bu modül, orijinal projedeki `hotelrunner.py` ile BİREBİR aynı fonksiyon imzalarını
(`quote`, `booking_link`, `format_try`, `_shift_past_dates`, `_norm_rooms`, `_day_count`,
`_fmt_date`, `_guest_summary`, `HotelRunnerError`) sunar.

Böylece:
1. Demo aşamasında dış ağa veya gerçek bir otelin rezervasyon sistemine bağımlı olmadan
   %100 deterministik, hızlı ve gerçekçi Çukurova/Kızkalesi butik otel fiyatları üretir.
2. Gerçek bir otel müşterisi bağlandığında (HotelRunner, ElektraWeb, Sedna vb.) yalnızca
   bu dosya değiştirilir; `agent.py` ve karar kapıları hiç bozulmadan çalışmaya devam eder.
"""

from __future__ import annotations

import json
import urllib.parse
from datetime import date, datetime, timedelta, timezone

from config import CONFIG
from decisions import filter_accessible_rooms, format_try

CURRENCY = "TRY"
LOCALE = "tr"
SEARCH_PAGE = f"{CONFIG.hotel_website.rstrip('/')}/rezervasyon"


class HotelRunnerError(RuntimeError):
    """Fiyat çekme sırasında kurtarılamayan hata."""


# Oda tanımları: taban gecelik fiyat (2 yetişkin, Oda+Kahvaltı BB, bahar/güz sezonu)
_ROOM_CATALOG = [
    {
        "code": "room_standard",
        "name": "Standart Bahçe Manzaralı Oda",
        "max_adults": 3,
        "max_guests": 3,
        "base_bb_2p": 3600.0,
        "accessible": False,
    },
    {
        "code": "room_engelsiz",
        "name": "Engelsiz / Erişilebilir Bahçe Odası",
        "max_adults": 2,
        "max_guests": 3,
        "base_bb_2p": 3600.0,
        "accessible": True,
    },
    {
        "code": "room_deluxe_sea",
        "name": "Deluxe Deniz & Kızkalesi Manzaralı Oda",
        "max_adults": 3,
        "max_guests": 3,
        "base_bb_2p": 4800.0,
        "accessible": False,
    },
    {
        "code": "room_family",
        "name": "Aile Odası (Ara Kapılı 2 Odalı)",
        "max_adults": 4,
        "max_guests": 5,
        "base_bb_2p": 6400.0,
        "accessible": False,
    },
    {
        "code": "room_suite_jacuzzi",
        "name": "Korykos Teras Suit (Jakuzili)",
        "max_adults": 2,
        "max_guests": 3,
        "base_bb_2p": 8200.0,
        "accessible": False,
    },
]

# Yarım pansiyon (akşam yemeği) kişi başı gecelik farkı
_HB_SUPPLEMENT_PER_ADULT = 750.0
_HB_SUPPLEMENT_PER_PAID_CHILD = 375.0

# Demo için "dolu" (müsait olmayan) örnek tarihler: alternatif tarih önerme (F-009) kuralını
# canlıda ve sınavda göstermek için her ayın 15-16 geceleri dolu simüle edilir.
_SOLD_OUT_MONTH_DAYS = {(7, 18), (8, 15)}


def _norm_rooms(rooms: list[dict]) -> list[dict]:
    out = []
    for r in rooms or []:
        adult = int(r.get("adult_count") or 0)
        child = int(r.get("child_count") or 0)
        ages = [int(a) for a in (r.get("child_ages") or [])]
        out.append({
            "adult_count": adult,
            "child_count": child,
            "child_ages": ages,
            "guest_count": adult + child,
        })
    return out or [{"adult_count": 2, "child_count": 0, "child_ages": [], "guest_count": 2}]


def _day_count(checkin: str, checkout: str) -> int:
    d1 = datetime.strptime(checkin, "%Y-%m-%d").date()
    d2 = datetime.strptime(checkout, "%Y-%m-%d").date()
    return max((d2 - d1).days, 1)


def _add_year(d: date) -> date:
    try:
        return d.replace(year=d.year + 1)
    except ValueError:
        return d.replace(year=d.year + 1, day=28)


def _shift_past_dates(checkin: str, checkout: str) -> tuple[str, str]:
    d1 = datetime.strptime(checkin, "%Y-%m-%d").date()
    d2 = datetime.strptime(checkout, "%Y-%m-%d").date()
    today = datetime.now(timezone.utc).date()
    while d1 < today:
        d1 = _add_year(d1)
        d2 = _add_year(d2)
    return d1.isoformat(), d2.isoformat()


def booking_link(checkin: str, checkout: str, rooms: list[dict]) -> str:
    search = {
        "checkin": checkin,
        "checkout": checkout,
        "nights": _day_count(checkin, checkout),
        "rooms": len(rooms),
        "adults": sum(r["adult_count"] for r in rooms),
        "children": sum(r["child_count"] for r in rooms),
    }
    q = urllib.parse.urlencode(search)
    return f"{SEARCH_PAGE}?{q}&lang={LOCALE}&currency={CURRENCY}"


def _season_multiplier(d: date) -> float:
    """Mersin/Kızkalesi sezon çarpanı + Cuma/Cumartesi hafta sonu farkı."""
    m = d.month
    if m in (7, 8):
        mult = 1.35  # Yüksek yaz sezonu
    elif m in (6, 9):
        mult = 1.15  # Sıcak Akdeniz sezonu
    elif m in (4, 5, 10):
        mult = 1.00  # Bahar / Omuz sezon
    else:
        mult = 0.85  # Kış sezonu (Kasım - Mart)
    # Cuma (4) ve Cumartesi (5) geceleri %10 hafta sonu farkı
    if d.weekday() in (4, 5):
        mult *= 1.10
    return mult


def _is_range_sold_out(d1: date, d2: date) -> bool:
    cur = d1
    while cur < d2:
        if (cur.month, cur.day) in _SOLD_OUT_MONTH_DAYS:
            return True
        cur += timedelta(days=1)
    return False


def _price_single_room_type(rt: dict, d1: date, d2: date, room_req: dict) -> dict | None:
    adults = room_req["adult_count"]
    children = room_req["child_count"]
    ages = room_req["child_ages"]
    total_guests = adults + children

    if adults > rt["max_adults"] or total_guests > rt["max_guests"]:
        return None

    # Kişi çarpanı: taban fiyat 2 yetişkin içindir.
    if adults == 1:
        pax_factor = 0.85
    elif adults == 2:
        pax_factor = 1.00
    elif adults == 3:
        pax_factor = 1.30
    else:
        pax_factor = 1.55

    # Çocuk politikası: 0-6 yaş ilk çocuk ücretsiz, 7-11 yaş çocuk başı +%15
    paid_children = sum(1 for a in ages if 7 <= a <= 11)
    extra_free_kids = max(0, sum(1 for a in ages if a <= 6) - 1)
    paid_children += extra_free_kids
    pax_factor += paid_children * 0.15

    nights = max((d2 - d1).days, 1)
    bb_total = 0.0
    cur = d1
    while cur < d2:
        bb_total += rt["base_bb_2p"] * _season_multiplier(cur) * pax_factor
        cur += timedelta(days=1)

    bb_total = round(bb_total / 50.0) * 50.0
    hb_add = nights * (adults * _HB_SUPPLEMENT_PER_ADULT + paid_children * _HB_SUPPLEMENT_PER_PAID_CHILD)
    hb_total = round((bb_total + hb_add) / 50.0) * 50.0

    boards = [
        {
            "meal_plan_code": "bed-breakfast",
            "meal_plan": "Oda + Kahvaltı",
            "total": bb_total,
            "per_night": round(bb_total / nights, 2),
            "currency": CURRENCY,
            "refundable": True,
            "rate_name": "Esnek İptal Tarifesi (Oda + Kahvaltı)",
        },
        {
            "meal_plan_code": "half-board",
            "meal_plan": "Yarım Pansiyon",
            "total": hb_total,
            "per_night": round(hb_total / nights, 2),
            "currency": CURRENCY,
            "refundable": True,
            "rate_name": "Esnek İptal Tarifesi (Yarım Pansiyon)",
        },
    ]

    cheapest = boards[0]
    return {
        "name": rt["name"],
        "boards": boards,
        "meal_plan": cheapest["meal_plan"],
        "meal_plan_code": cheapest["meal_plan_code"],
        "total": cheapest["total"],
        "per_night": cheapest["per_night"],
        "currency": CURRENCY,
        "availability": 3,
        "refundable": True,
        "rate_name": cheapest["rate_name"],
    }


_TR_MONTHS = [
    "", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
    "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
]

_BOARD_HEADINGS = {
    "bed-breakfast": "Oda + Kahvaltı (açık büfe/serpme Akdeniz kahvaltısı dahil)",
    "half-board": "Yarım Pansiyon (kahvaltı + akşam yemeği dahil)",
}


def _fmt_date(d: str) -> str:
    dt = datetime.strptime(d, "%Y-%m-%d").date()
    return f"{dt.day} {_TR_MONTHS[dt.month]} {dt.year}"


def _guest_summary(rooms: list[dict]) -> str:
    a = sum(r["adult_count"] for r in rooms)
    c = sum(r["child_count"] for r in rooms)
    parts = [f"{a} yetişkin"]
    if c:
        parts.append(f"{c} çocuk")
    if len(rooms) > 1:
        parts.append(f"{len(rooms)} oda")
    return ", ".join(parts)


def _msg_available(checkin: str, checkout: str, rooms: list[dict], nights: int, results: list[dict]) -> str:
    head = (
        f"{_fmt_date(checkin)} - {_fmt_date(checkout)} ({nights} gece), "
        f"{_guest_summary(rooms)} için müsait oda ve toplam konaklama fiyatlarımız:"
    )
    blocks = []
    for code in ("bed-breakfast", "half-board"):
        entries = []
        for r in results:
            b = next((x for x in (r.get("boards") or []) if x["meal_plan_code"] == code), None)
            if b:
                entries.append((b["total"], r["name"]))
        if not entries:
            continue
        entries.sort(key=lambda e: e[0])
        heading = _BOARD_HEADINGS.get(code, code)
        rows = [f"- {name}: {format_try(total)}" for total, name in entries]
        blocks.append(f"{heading}:\n" + "\n".join(rows))

    footer = f"({nights} gecelik tüm vergiler dahil oda toplam fiyatlarıdır.)"
    return head + "\n\n" + "\n\n".join(blocks) + "\n\n" + footer


def _msg_unavailable(checkin: str, checkout: str, rooms: list[dict]) -> str:
    return (
        f"{_fmt_date(checkin)} - {_fmt_date(checkout)} tarihlerinde "
        f"{_guest_summary(rooms)} kapasitesine uygun müsait odamız bulunmuyor."
    )


def quote(
    checkin: str,
    checkout: str,
    rooms: list[dict] | None = None,
    include_accessible: bool = False,
) -> dict:
    """Müsaitlik ve konaklama fiyatlarını hesaplar."""
    rooms = _norm_rooms(rooms or [])
    checkin, checkout = _shift_past_dates(checkin, checkout)
    nights = _day_count(checkin, checkout)
    link = booking_link(checkin, checkout, rooms)

    d1 = datetime.strptime(checkin, "%Y-%m-%d").date()
    d2 = datetime.strptime(checkout, "%Y-%m-%d").date()

    if _is_range_sold_out(d1, d2):
        return {
            "available": False,
            "checkin": checkin,
            "checkout": checkout,
            "nights": nights,
            "link": link,
            "rooms": [],
            "message": _msg_unavailable(checkin, checkout, rooms),
        }

    primary_req = rooms[0]
    results = []
    for rt in _ROOM_CATALOG:
        priced = _price_single_room_type(rt, d1, d2, primary_req)
        if priced:
            results.append(priced)

    results.sort(key=lambda x: x["total"])
    results = filter_accessible_rooms(results, include_accessible)

    if not results:
        return {
            "available": False,
            "checkin": checkin,
            "checkout": checkout,
            "nights": nights,
            "link": link,
            "rooms": [],
            "message": _msg_unavailable(checkin, checkout, rooms),
        }

    return {
        "available": True,
        "checkin": checkin,
        "checkout": checkout,
        "nights": nights,
        "link": link,
        "rooms": results,
        "message": _msg_available(checkin, checkout, rooms, nights, results),
    }


if __name__ == "__main__":
    import sys
    ci = sys.argv[1] if len(sys.argv) > 1 else "2027-06-18"
    co = sys.argv[2] if len(sys.argv) > 2 else "2027-06-20"
    ad = int(sys.argv[3]) if len(sys.argv) > 3 else 2
    res = quote(ci, co, [{"adult_count": ad, "child_count": 0, "child_ages": []}])
    print(json.dumps(res, ensure_ascii=False, indent=2))

