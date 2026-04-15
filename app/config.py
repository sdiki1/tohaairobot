from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    bot_token: str
    google_api_key: str
    vertex_project: str | None
    vertex_location: str
    vertex_model: str
    attach_dir: Path
    admin_host: str
    admin_port: int
    admin_token: str
    top_k_chunks: int
    chunk_size: int
    chunk_overlap: int
    request_timeout_seconds: int
    model_max_output_tokens: int
    model_temperature: float
    log_level: str
    public_base_url: str | None
    allow_unauthorized_admin: bool


def load_settings() -> Settings:
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    google_api_key = os.getenv("GOOGLE_API_KEY", "").strip()
    admin_token = os.getenv("ADMIN_TOKEN", "").strip()

    if not bot_token:
        raise RuntimeError("BOT_TOKEN is required")
    if not google_api_key:
        raise RuntimeError("GOOGLE_API_KEY is required")
    if not admin_token and not _as_bool(os.getenv("ALLOW_UNAUTHORIZED_ADMIN"), False):
        raise RuntimeError(
            "ADMIN_TOKEN is required unless ALLOW_UNAUTHORIZED_ADMIN=true (not recommended)"
        )

    attach_dir = Path(os.getenv("ATTACH_DIR", "attach")).resolve()
    return Settings(
        bot_token=bot_token,
        google_api_key=google_api_key,
        vertex_project=(os.getenv("VERTEX_PROJECT") or "").strip() or None,
        vertex_location=(os.getenv("VERTEX_LOCATION") or "us-central1").strip(),
        vertex_model=(os.getenv("VERTEX_MODEL") or "gemini-2.5-flash").strip(),
        attach_dir=attach_dir,
        admin_host=(os.getenv("ADMIN_HOST") or "0.0.0.0").strip(),
        admin_port=int(os.getenv("ADMIN_PORT") or "8080"),
        admin_token=admin_token,
        top_k_chunks=int(os.getenv("TOP_K_CHUNKS") or "6"),
        chunk_size=int(os.getenv("CHUNK_SIZE") or "1400"),
        chunk_overlap=int(os.getenv("CHUNK_OVERLAP") or "250"),
        request_timeout_seconds=int(os.getenv("REQUEST_TIMEOUT_SECONDS") or "60"),
        model_max_output_tokens=int(os.getenv("MODEL_MAX_OUTPUT_TOKENS") or "1024"),
        model_temperature=float(os.getenv("MODEL_TEMPERATURE") or "0.2"),
        log_level=(os.getenv("LOG_LEVEL") or "info").strip().lower(),
        public_base_url=(os.getenv("PUBLIC_BASE_URL") or "").strip() or None,
        allow_unauthorized_admin=_as_bool(os.getenv("ALLOW_UNAUTHORIZED_ADMIN"), False),
    )
