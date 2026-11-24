"""Merkezi yapılandırma: _knowledge/credentials/master.env + proje .env dosyasından yükler.

Otel_DM_Demo: Korykos Boutique Hotel & Beach (Mersin Kızkalesi) demo asistanı.
Ana sohbet, ses çevirisi ve görsel okuma tamamen OpenAI üzerinden çalışır.
Personel devir bildirimleri Telegram üzerinden iletilir.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent
MASTER_ENV = PROJECT_ROOT.parent.parent / "_knowledge" / "credentials" / "master.env"
LOCAL_ENV = PROJECT_ROOT / ".env"

if MASTER_ENV.exists():
    load_dotenv(MASTER_ENV)
if LOCAL_ENV.exists():
    load_dotenv(LOCAL_ENV, override=True)


@dataclass(frozen=True)
class Config:
    # --- Otel Kimliği ---
    hotel_name: str
    hotel_phone: str
    hotel_whatsapp: str
    hotel_email: str
    hotel_website: str
    # --- OpenAI (Sohbet + Ses + Görsel) ---
    openai_api_key: str | None
    agent_model: str
    transcribe_model: str
    vision_model: str
    vision_max_mb: int
    # --- Telegram (Personel Bildirimi / Escalation) ---
    telegram_bot_token: str | None
    admin_chat_id: str | None
    # --- ManyChat & Supabase (Aşama 2 ve 3 için hazır, opsiyonel) ---
    manychat_token: str | None
    supabase_url: str | None
    supabase_service_key: str | None
    # --- Medya & Coalesce ---
    media_probe_timeout: float
    coalesce_initial_ms: int
    coalesce_straggler_ms: int
    coalesce_max_iter: int
    coalesce_pool_size: int
    # --- Davranış ---
    history_window: int
    dry_run: bool

    @staticmethod
    def from_env() -> "Config":
        return Config(
            hotel_name=os.getenv("HOTEL_NAME", "Korykos Boutique Hotel & Beach"),
            hotel_phone=os.getenv("HOTEL_PHONE", "+90 324 523 00 42"),
            hotel_whatsapp=os.getenv("HOTEL_WHATSAPP", "+90 532 000 33 42"),
            hotel_email=os.getenv("HOTEL_EMAIL", "info@korykoshotel.com"),
            hotel_website=os.getenv("HOTEL_WEBSITE", "https://www.korykoshotel.com"),
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            agent_model=os.getenv("HOTEL_AGENT_MODEL", "gpt-4.1-mini"),
            transcribe_model=os.getenv("HOTEL_TRANSCRIBE_MODEL", "gpt-4o-mini-transcribe"),
            vision_model=os.getenv("HOTEL_VISION_MODEL", "gpt-4o-mini"),
            vision_max_mb=int(os.getenv("HOTEL_VISION_MAX_MB", "8")),
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN"),
            admin_chat_id=os.getenv("ADMIN_CHAT_ID"),
            manychat_token=os.getenv("MANYCHAT_API_TOKEN") or os.getenv("CAM_MANYCHAT_TOKEN"),
            supabase_url=os.getenv("SUPABASE_URL"),
            supabase_service_key=os.getenv("SUPABASE_SERVICE_ROLE_KEY"),
            media_probe_timeout=float(os.getenv("HOTEL_MEDIA_PROBE_TIMEOUT", "5")),
            coalesce_initial_ms=int(os.getenv("COALESCE_INITIAL_MS", "2500")),
            coalesce_straggler_ms=int(os.getenv("COALESCE_STRAGGLER_MS", "1200")),
            coalesce_max_iter=int(os.getenv("COALESCE_MAX_ITER", "4")),
            coalesce_pool_size=int(os.getenv("COALESCE_POOL_SIZE", "16")),
            history_window=int(os.getenv("HOTEL_HISTORY_WINDOW", "15")),
            dry_run=os.getenv("HOTEL_DRY_RUN", "0") == "1",
        )


CONFIG = Config.from_env()

