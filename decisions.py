"""Saf, yan-etkisiz karar fonksiyonları — Korykos Boutique Hotel & Beach (Otel_DM_Demo).

Orijinal Otel_Danisma_Asistani projesindeki deterministik güvenlik kapılarının (validate_booking,
reclassify_ages, headcount_mismatch, alternative_windows, wants_accessible, spa_context_without_room,
contains_price_mention) yeni otel bilgilerine uyarlanmış sürümüdür.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

GROUP_MSG = (
    "20 ve üzeri kişilik grup konaklamaları ve etkinlikler için özel grup indirimi uyguluyoruz. "
    "Lütfen info@korykoshotel.com adresine yazın veya +90 324 523 00 42 numaralı hattımızdan bize ulaşın."
)


def validate_booking(checkin: str, checkout: str, rooms: list[dict]) -> str | None:
    """get_price öncesi deterministik kapı."""
    try:
        d1 = datetime.strptime(checkin, "%Y-%m-%d").date()
        d2 = datetime.strptime(checkout, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return "Tarihleri tam anlayamadım. Giriş ve çıkış tarihini gün/ay/yıl olarak yazar mısınız?"
    if d2 <= d1:
        return "Çıkış tarihi giriş tarihinden sonra olmalı. Doğru çıkış tarihini paylaşır mısınız?"
    total_adult = sum(int(r.get("adult_count") or 0) for r in rooms)
    total_child = sum(int(r.get("child_count") or 0) for r in rooms)
    if total_adult < 1:
        return "Konaklayacak yetişkin sayısını öğrenebilir miyim?"
    for r in rooms:
        cc = int(r.get("child_count") or 0)
        ages = r.get("child_ages") or []
        if cc > 0 and len(ages) != cc:
            return (
                "Çocuk sayısı ile yaşları eşleşmiyor. Her çocuğun yaşını paylaşır mısınız? "
                "(0-6 yaş ilk çocuk ücretsiz, 7-11 yaş çocuk indirimli, 12 ve üzeri yetişkin sayılır.)"
            )
    if (total_adult + total_child) >= 20:
        return GROUP_MSG
    return None


ADULT_AGE = 12


def reclassify_ages(rooms: list[dict]) -> list[dict]:
    """child_ages içindeki 12+ yaşları adult_count'a taşır (11 ve altı çocuk kalır)."""
    out = []
    for r in rooms or []:
        try:
            ages = [int(a) for a in (r.get("child_ages") or [])]
            adults_from_age = [a for a in ages if a >= ADULT_AGE]
            if adults_from_age:
                child_ages = [a for a in ages if a < ADULT_AGE]
                r = {
                    **r,
                    "adult_count": int(r.get("adult_count") or 0) + len(adults_from_age),
                    "child_ages": child_ages,
                    "child_count": len(child_ages),
                }
        except (TypeError, ValueError):
            pass
        out.append(r)
    return out


_TR_MAP_HEADCOUNT = str.maketrans("şŞıİüÜöÖçÇğĞâîû", "sSiIuUoOcCgGaiu")
_STATED_ADULT_RE = re.compile(r"(\d+)\s*yetiskin")
_STATED_CHILD_RE = re.compile(r"(\d+)\s*cocu[kg]")
_AGE_RUN_RE = re.compile(r"((?:\d+\s*(?:bucuk)?\s*(?:,|ve|ile|/|-|\s)\s*)*\d+)\s*(?:bucuk\s*)?yas")
_DIGITS_RE = re.compile(r"\d+")
MAX_CHILD_AGE = 17

HEADCOUNT_MISMATCH_MSG = (
    "Kişi sayısında bir tutarsızlık fark ettim; toplam kaç yetişkin ve kaç çocuk "
    "olduğunuzu (çocuklarınız varsa yaşlarıyla birlikte) tekrar belirtir misiniz?"
)


def _norm_tr(text: str) -> str:
    return (text or "").translate(_TR_MAP_HEADCOUNT).lower()


def stated_headcount(text: str) -> tuple[int | None, int | None]:
    norm = _norm_tr(text)

    def _single(matches: list[str]) -> int | None:
        vals = {int(m) for m in matches}
        return vals.pop() if len(vals) == 1 else None

    return (
        _single(_STATED_ADULT_RE.findall(norm)),
        _single(_STATED_CHILD_RE.findall(norm)),
    )


def stated_child_ages(text: str) -> list[int] | None:
    ages: list[int] = []
    for run in _AGE_RUN_RE.findall(_norm_tr(text)):
        ages.extend(int(n) for n in _DIGITS_RE.findall(run))
    if any(a > MAX_CHILD_AGE for a in ages):
        return None
    return ages


def expected_headcount(text: str) -> tuple[int | None, int | None] | None:
    stated_adult, stated_child = stated_headcount(text)
    if stated_adult is None and stated_child is None:
        return None
    ages = stated_child_ages(text)
    if ages is None:
        return None
    promoted = sum(1 for a in ages if a >= ADULT_AGE)
    if stated_child is not None and (len(ages) > stated_child or promoted > stated_child):
        return None
    expected_adult = None if stated_adult is None else stated_adult + promoted
    expected_child = None if stated_child is None else stated_child - promoted
    return (expected_adult, expected_child)


def _headcount_matches(expected: tuple[int | None, int | None], adult: int, child: int) -> bool:
    exp_a, exp_c = expected
    if exp_a is not None and exp_a != adult:
        return False
    if exp_c is not None and exp_c != child:
        return False
    return True


def headcount_mismatch(text: str, rooms: list[dict]) -> bool:
    expected = expected_headcount(text)
    if expected is None:
        return False
    normalized = reclassify_ages(rooms or [])
    total_adult = sum(int(r.get("adult_count") or 0) for r in normalized)
    total_child = sum(int(r.get("child_count") or 0) for r in normalized)
    if _headcount_matches(expected, total_adult, total_child):
        return False
    if len(normalized) > 1:
        for r in normalized:
            if _headcount_matches(
                expected,
                int(r.get("adult_count") or 0),
                int(r.get("child_count") or 0),
            ):
                return False
    return True


ALTERNATIVE_SHIFTS = (1, -1, 2, -2, 7)


def alternative_windows(
    checkin: str,
    checkout: str,
    today: str | None = None,
    shifts: tuple[int, ...] = ALTERNATIVE_SHIFTS,
    limit: int = 3,
) -> list[tuple[str, str]]:
    try:
        d1 = datetime.strptime(checkin, "%Y-%m-%d").date()
        d2 = datetime.strptime(checkout, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return []
    nights = (d2 - d1).days
    if nights < 1:
        return []
    floor = None
    if today:
        try:
            bugun = datetime.strptime(today[:10], "%Y-%m-%d").date()
            floor = bugun if d1 > bugun else None
        except (ValueError, TypeError):
            floor = None
    out: list[tuple[str, str]] = []
    for shift in shifts:
        yeni_giris = d1 + timedelta(days=shift)
        if floor and yeni_giris <= floor:
            continue
        yeni_cikis = yeni_giris + timedelta(days=nights)
        out.append((yeni_giris.isoformat(), yeni_cikis.isoformat()))
        if len(out) >= limit:
            break
    return out


_TR_MAP = str.maketrans("şŞıİüÜöÖçÇğĞâîû", "sSiIuUoOcCgGaiu")
_ACCESS_TRIGGERS = (
    "engelli", "engelsiz", "erisilebilir", "tekerlekli", "wheelchair", "accessible",
    "yurume guclu", "hareket kisit", "yatalak", "yasli",
)


def wants_accessible(text: str) -> bool:
    norm = (text or "").translate(_TR_MAP).lower()
    return any(k in norm for k in _ACCESS_TRIGGERS)


_SPA_DAYUSE_TRIGGERS = (
    "havuz", "hamam", "spa", "sauna", "kese", "kopuk",
    "masaj", "gunubirlik", "day use", "wellness", "plaj", "sezlong",
)
_LODGING_TRIGGERS = (
    "oda", "room", "konaklama", "suit", "suite", "gece", "kahvalti", "pansiyon", "rezervasyon",
    "kisilik", "deluxe", "standart", "aile", "teras", "engelsiz", "engelli",
)


def spa_context_without_room(text: str) -> bool:
    norm = (text or "").translate(_TR_MAP).lower()
    has_spa = any(k in norm for k in _SPA_DAYUSE_TRIGGERS)
    has_lodging = any(k in norm for k in _LODGING_TRIGGERS)
    return has_spa and not has_lodging


def format_try(amount: float) -> str:
    s = f"{amount:,.2f}"
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    if s.endswith(",00"):
        s = s[:-3]
    return f"{s} TL"


_ACCESSIBLE_NAME_RE = re.compile(r"\bengel(li|siz)\b", re.I)


def is_accessible_room(name: str | None) -> bool:
    return bool(_ACCESSIBLE_NAME_RE.search(name or ""))


def filter_accessible_rooms(results: list[dict], include_accessible: bool) -> list[dict]:
    if include_accessible:
        return results
    visible = [r for r in results if not is_accessible_room(r.get("name"))]
    return visible if visible else results


_PRICE_MENTION_RE = re.compile(r"\d[\d.,]*\s*(?:TL\b|₺|TRY\b)", re.IGNORECASE)


def contains_price_mention(text: str) -> bool:
    return bool(_PRICE_MENTION_RE.search(text or ""))


PRICE_NOT_GROUNDED_FALLBACK = (
    "Bu tutarı şu anda kesin olarak doğrulayamadım. Güncel fiyatı öğrenmek için lütfen "
    "giriş-çıkış tarihlerinizi ve kişi sayısını tekrar yazar mısınız, ya da +90 324 523 00 42 "
    "numaralı hattımızdan bize ulaşabilirsiniz."
)

