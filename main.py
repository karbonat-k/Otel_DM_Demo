"""Korykos Boutique Hotel & Beach (Otel_DM_Demo) — FastAPI servisi + CLI Sohbet + Web Demo API.

Endpoint'ler:
  GET  /health      — sağlık kontrolü
  POST /price       — müsaitlik + konaklama fiyatı
  POST /chat        — doğrudan senkron sohbet ucu (Web demo ekranı ve testler için)
  POST /webhook     — ManyChat'ten gelen Instagram/WhatsApp/Facebook mesajları

Terminalde interaktif sohbet için:
  python main.py --cli
"""

from __future__ import annotations

import logging
import os
import sys

from pathlib import Path
import requests
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import hotelrunner
from config import CONFIG

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("otel_demo")

PRICE_SHARED_SECRET = os.getenv("PRICE_SHARED_SECRET", "")
PRICE_PUBLIC = os.getenv("PRICE_PUBLIC", "1") == "1"
WEBHOOK_SECRET = os.getenv("HOTEL_WEBHOOK_SECRET", "")
_VERIFY_SSL = os.getenv("HOTELRUNNER_VERIFY_SSL", "1") != "0"

_AUDIO_FAIL = "Sesli mesajınızı anlayamadım, kısaca yazabilir misiniz?"
_IMAGE_FAIL = "Gönderdiğiniz görseli şu an inceleyemedim. Sormak istediğinizi kısaca yazabilir misiniz?"
_MEDIA_FAIL = "Gönderdiğiniz içeriği şu an inceleyemedim. Sormak istediğinizi kısaca yazabilir misiniz?"

app = FastAPI(title="Korykos Boutique Hotel & Beach DM Asistanı", version="1.0.0")

_STATIC_DIR = Path(__file__).resolve().parent / "static"
_STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


class RoomIn(BaseModel):
    adult_count: int = 2
    child_count: int = 0
    child_ages: list[int] = Field(default_factory=list)


class PriceRequest(BaseModel):
    checkin_date: str
    checkout_date: str
    rooms: list[RoomIn] | None = None
    adult_count: int | None = None
    child_count: int | None = None
    child_ages: list[int] = Field(default_factory=list)
    room_count: int | None = None


class ChatRequest(BaseModel):
    message: str
    user_id: str = "web_demo_user"
    platform: str = "Instagram"
    reset: bool = False


def _rooms_from_request(req: PriceRequest) -> list[dict]:
    if req.rooms:
        return [r.model_dump() for r in req.rooms]
    adult = req.adult_count if req.adult_count is not None else 2
    child = req.child_count or 0
    ages = req.child_ages or []
    n = req.room_count or 1
    return [{"adult_count": adult, "child_count": child, "child_ages": ages} for _ in range(max(n, 1))]


@app.get("/", response_class=HTMLResponse)
def demo_page() -> str:
    html_path = Path(__file__).resolve().parent / "demo_ui.html"
    if html_path.exists():
        return html_path.read_text(encoding="utf-8")
    return "<h1>Otel DM Demo Servisi Aktif</h1>"


@app.get("/health")
def health() -> dict:
    delivery_ready = CONFIG.dry_run or bool(CONFIG.manychat_token)
    return {
        "status": "ok",
        "service": "otel-dm-demo",
        "hotel": CONFIG.hotel_name,
        "delivery_ready": delivery_ready,
        "dry_run": CONFIG.dry_run,
    }


@app.post("/price")
def price(req: PriceRequest, x_price_key: str | None = Header(default=None)) -> dict:
    if not PRICE_PUBLIC:
        if not PRICE_SHARED_SECRET or x_price_key != PRICE_SHARED_SECRET:
            raise HTTPException(status_code=401, detail="unauthorized")
    rooms = _rooms_from_request(req)
    return hotelrunner.quote(req.checkin_date, req.checkout_date, rooms, include_accessible=True)


@app.post("/chat")
def chat_endpoint(req: ChatRequest) -> dict:
    """Web demo arayüzü ve hızlı test için senkron sohbet ucu."""
    import agent
    import images
    import memory

    if req.reset:
        memory.clear(req.user_id)

    history = memory.load(req.user_id)
    result = agent.respond(
        req.message,
        history=history,
        user_id=req.user_id,
        platform=req.platform,
    )
    answer = (result.get("text") or "").strip() or agent.FALLBACK_TEXT
    memory.save(req.user_id, req.platform, "user", req.message)
    memory.save(req.user_id, req.platform, "assistant", answer)
    img_keys = result.get("image_keys") or []
    if img_keys:
        memory.save(req.user_id, req.platform, "system", images.format_sent_marker(img_keys))
    return {
        "reply": answer,
        "link": result.get("link"),
        "images": result.get("images") or [],
        "image_keys": img_keys,
        "escalated": bool(result.get("escalated")),
        "escalation_info": result.get("escalation_info"),
    }


def _extract(payload: dict) -> tuple[str | None, str | None, str | None]:
    b = payload.get("body") if isinstance(payload.get("body"), dict) else payload
    user_id = b.get("kullanici_id") or b.get("subscriber_id") or b.get("user_id")
    message = b.get("last_text_input") or b.get("message") or b.get("text")
    platform = b.get("platform")
    return user_id, message, platform


def _transcribe_audio(url: str) -> str | None:
    try:
        import llm
        r = requests.get(
            url,
            timeout=20,
            verify=_VERIFY_SSL,
            headers={"User-Agent": "Mozilla/5.0 (compatible; KorykosBot/2.0)"},
        )
        r.raise_for_status()
        text = llm.transcribe(r.content, filename="audio.mp4")
        log.info("audio transcribed: %s", (text or "")[:80])
        return text or None
    except Exception as e:
        log.warning("transcribe failed: %s", e)
        return None


def _resolve_message(raw: str) -> tuple[str | None, str]:
    import media
    kind = media.classify_media_url(raw)
    if kind == "audio":
        return (_transcribe_audio(raw), "audio")
    if kind == "image":
        import vision
        desc = vision.describe_image(raw)
        if not desc:
            return (None, "image")
        return (f"[Misafir bir görsel gönderdi: {desc}]", "image")
    return (raw, "text")


def _process_batch(user_id: str, platform: str, raw_messages: list[str]) -> None:
    import agent
    import images
    import manychat
    import memory

    resolved: list[str] = []
    failed_kinds: set[str] = set()
    for raw in raw_messages:
        try:
            text, kind = _resolve_message(raw)
        except Exception as e:
            log.exception("resolve error user=%s: %s", user_id, e)
            text, kind = None, "text"
        if text:
            resolved.append(text)
        elif kind in ("audio", "image"):
            failed_kinds.add(kind)

    if not resolved:
        if failed_kinds:
            msg = (
                _AUDIO_FAIL if failed_kinds == {"audio"}
                else _IMAGE_FAIL if failed_kinds == {"image"}
                else _MEDIA_FAIL
            )
            try:
                manychat.deliver_answer(user_id, platform, msg, None)
            except Exception as e:
                log.warning("media-fail deliver error user=%s: %s", user_id, e)
        return

    combined = " ".join(resolved)

    try:
        history = memory.load(user_id)
        result = agent.respond(combined, history, user_id=user_id, platform=platform)
        answer = (result.get("text") or "").strip() or agent.FALLBACK_TEXT
        link = result.get("link")
        imgs = result.get("images") or []
        img_keys = result.get("image_keys") or []
    except Exception as e:
        log.exception("agent error user=%s: %s", user_id, e)
        answer, link, imgs, img_keys = agent.FALLBACK_TEXT, None, [], []

    try:
        delivered = manychat.deliver_answer(user_id, platform, answer, link)
        memory.save(user_id, platform, "user", combined)
        if delivered:
            memory.save(user_id, platform, "assistant", answer)
            if imgs:
                sent_imgs = manychat.send_images(user_id, platform, imgs)
                if sent_imgs and img_keys:
                    memory.save(user_id, platform, "system", images.format_sent_marker(img_keys))
    except Exception as e:
        log.exception("deliver/save error user=%s: %s", user_id, e)


@app.post("/webhook")
async def webhook(request: Request, x_webhook_secret: str | None = Header(default=None)) -> dict:
    if not WEBHOOK_SECRET or x_webhook_secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="invalid or missing webhook secret")
    payload = await request.json()
    user_id, message, platform = _extract(payload)
    if not user_id or not message or not platform:
        return {"status": "ignored", "reason": "missing fields"}
    import coalesce
    coalesce.enqueue(user_id, platform, message, _process_batch)
    return {"status": "received"}


def run_cli() -> None:
    """Terminal üzerinden botla canlı yazışma modu."""
    import agent
    import images
    import memory

    user_id = "onat_cli_test"
    print("=" * 68)
    print(f"🏨 {CONFIG.hotel_name} — Canlı DM Botu Test Ekranı")
    print("Çıkmak için 'cikis' veya 'q', hafızayı sıfırlamak için 'sifirla' yazın.")
    print("=" * 68)
    while True:
        try:
            msg = input("\n👤 Misafir: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGörüşmek üzere!")
            break
        if not msg:
            continue
        if msg.lower() in ("q", "quit", "exit", "cikis", "çıkış"):
            print("Görüşmek üzere!")
            break
        if msg.lower() in ("sifirla", "sıfırla", "reset"):
            memory.clear(user_id)
            print("🔄 Konuşma geçmişi sıfırlandı.")
            continue

        history = memory.load(user_id)
        res = agent.respond(msg, history=history, user_id=user_id, platform="Instagram")
        reply = res.get("text", "")
        memory.save(user_id, "Instagram", "user", msg)
        memory.save(user_id, "Instagram", "assistant", reply)
        if res.get("image_keys"):
            memory.save(user_id, "Instagram", "system", images.format_sent_marker(res["image_keys"]))

        print(f"\n🤖 Bot: {reply}")
        if res.get("link"):
            print(f"🔗 Rezervasyon Linki: {res['link']}")
        if res.get("images"):
            print(f"📸 Gönderilen Fotoğraflar ({len(res['images'])} adet): {', '.join(res.get('image_keys') or [])}")
        if res.get("escalated"):
            print("🔔 [TELEGRAM BİLDİRİMİ GÖNDERİLDİ -> Otel Yetkilisine Devredildi]")


if __name__ == "__main__":
    if "--cli" in sys.argv:
        run_cli()
    else:
        import uvicorn
        uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))

