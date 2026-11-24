"""ManyChat API istemcisi — yanıtı Instagram / WhatsApp / Facebook misafirine ulaştırır."""

from __future__ import annotations

import logging
import os
import time as _time

import requests

from config import CONFIG

log = logging.getLogger("otel_demo.manychat")
_VERIFY_SSL = os.getenv("HOTELRUNNER_VERIFY_SSL", "1") != "0"
_BASE = "https://api.manychat.com/fb"
_TIMEOUT = 15

IMAGE_FIELD = os.getenv("MANYCHAT_IMAGE_FIELD", "14706284")

PLATFORMS = {
    "Instagram": {
        "answer_field": os.getenv("MC_IG_ANSWER_FIELD", "12768588"),
        "link_field": os.getenv("MC_IG_LINK_FIELD", "12794703"),
        "flow_no_link": os.getenv("MC_IG_FLOW_NO_LINK", "content20250402164949_247904"),
        "flow_with_link": os.getenv("MC_IG_FLOW_WITH_LINK", "content20250406115700_211180"),
        "wait_field": os.getenv("MC_IG_WAIT_FIELD", "13919949"),
        "wait_flow": os.getenv("MC_IG_WAIT_FLOW", "content20251107180919_090536"),
        "image_flow": os.getenv("MC_IG_IMAGE_FLOW", "content20260618180731_899730"),
    },
    "Facebook": {
        "answer_field": "12807221",
        "link_field": "12807223",
        "flow_no_link": "content20250713165410_471590",
        "flow_with_link": "content20250713165410_462736",
        "wait_field": "13919951",
        "wait_flow": "content20251107181323_087279",
        "image_flow": "content20260618180957_128546",
    },
    "Whatsapp": {
        "answer_field": "12907533",
        "link_field": "12907534",
        "flow_no_link": "content20250713171545_091569",
        "flow_with_link": "content20250713171545_082551",
        "wait_field": "13919950",
        "wait_flow": "content20250919153958_516965",
        "image_flow": "content20260618181028_068833",
    },
}

_IMAGE_SEND_DELAY = float(os.getenv("HOTEL_IMAGE_SEND_DELAY_S", "0.3"))


def _post(path: str, body: dict) -> bool:
    if CONFIG.dry_run:
        log.info("[DRY_RUN] ManyChat %s %s", path, {k: body[k] for k in body if k != "field_value"})
        return True
    if not CONFIG.manychat_token:
        log.error("MANYCHAT_API_TOKEN yok — ManyChat %s gönderilemedi", path)
        return False
    headers = {
        "Authorization": f"Bearer {CONFIG.manychat_token}",
        "Content-Type": "application/json",
    }
    try:
        r = requests.post(f"{_BASE}{path}", headers=headers, json=body, timeout=_TIMEOUT, verify=_VERIFY_SSL)
        if r.status_code >= 300:
            log.warning("ManyChat %s -> %s %s", path, r.status_code, r.text[:200])
            return False
        return True
    except Exception as e:
        log.warning("ManyChat %s hata: %s", path, e)
        return False


def set_custom_field(subscriber_id: str, field_id: str, value: str) -> bool:
    return _post(
        "/subscriber/setCustomField",
        {"subscriber_id": subscriber_id, "field_id": int(field_id), "field_value": value},
    )


def send_flow(subscriber_id: str, flow_ns: str) -> bool:
    return _post("/sending/sendFlow", {"subscriber_id": subscriber_id, "flow_ns": flow_ns})


def _cfg(platform: str) -> dict | None:
    if not platform:
        return None
    return PLATFORMS.get(platform) or PLATFORMS.get(platform.strip().capitalize())


def deliver_answer(subscriber_id: str, platform: str, message: str, link: str | None = None) -> bool:
    c = _cfg(platform)
    if not c:
        log.warning("Bilinmeyen platform: %s", platform)
        return False
    if not set_custom_field(subscriber_id, c["answer_field"], message):
        return False
    if link:
        if set_custom_field(subscriber_id, c["link_field"], link):
            return send_flow(subscriber_id, c["flow_with_link"])
        return send_flow(subscriber_id, c["flow_no_link"])
    return send_flow(subscriber_id, c["flow_no_link"])


def send_images(subscriber_id: str, platform: str, image_urls: list[str]) -> int:
    c = _cfg(platform)
    if not c or not c.get("image_flow"):
        return 0
    sent = 0
    urls = [u for u in (image_urls or []) if u]
    for i, url in enumerate(urls):
        if not set_custom_field(subscriber_id, IMAGE_FIELD, url):
            continue
        if send_flow(subscriber_id, c["image_flow"]):
            sent += 1
        if not CONFIG.dry_run and i < len(urls) - 1 and _IMAGE_SEND_DELAY > 0:
            _time.sleep(_IMAGE_SEND_DELAY)
    return sent

