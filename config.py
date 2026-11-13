"""Configuración de Tinkuy a partir de variables de entorno (y de un archivo .env opcional).

Ninguna clave se envía al navegador: el frontend solo recibe el *estado* de la
configuración (por ejemplo, «modelo configurado: sí/no»).
"""
from __future__ import annotations

import os
from pathlib import Path

try:  # python-dotenv es opcional
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None

ROOT = Path(__file__).resolve().parent.parent
if load_dotenv:
    load_dotenv(ROOT / ".env")


def _bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "sí", "si", "yes", "on"}


class Settings:
    def __init__(self) -> None:
        self.host = os.getenv("TINKUY_HOST", "127.0.0.1")
        self.port = int(os.getenv("TINKUY_PORT", "8642"))
        self.data_dir = Path(os.getenv("TINKUY_DATA_DIR", str(ROOT / "data")))
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "tinkuy.sqlite3"
        self.frontend_dir = ROOT / "frontend" / "public"
        self.timezone = os.getenv("TINKUY_TZ", "America/Lima")

        # --- Modelo de lenguaje -------------------------------------------------
        # anthropic | openai | replay | none
        self.llm_provider = os.getenv("TINKUY_LLM_PROVIDER", "anthropic").strip().lower()
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        self.anthropic_base_url = os.getenv("TINKUY_ANTHROPIC_BASE_URL", "https://api.anthropic.com").rstrip("/")
        self.anthropic_model = os.getenv("TINKUY_MODEL", "claude-sonnet-5-5").strip()
        self.openai_api_key = os.getenv("TINKUY_OPENAI_API_KEY", os.getenv("OPENAI_API_KEY", "")).strip()
        self.openai_base_url = os.getenv("TINKUY_OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.openai_model = os.getenv("TINKUY_OPENAI_MODEL", "gpt-4.1").strip()
        self.replay_dir = Path(os.getenv("TINKUY_REPLAY_DIR", str(ROOT / "tests" / "fixtures" / "replay")))
        self.llm_concurrency = max(1, int(os.getenv("TINKUY_LLM_CONCURRENCY", "3")))
        self.llm_timeout = int(os.getenv("TINKUY_LLM_TIMEOUT", "240"))
        self.llm_max_tokens = int(os.getenv("TINKUY_LLM_MAX_TOKENS", "8000"))
        self.vision_enabled = _bool("TINKUY_VISION", True)

        # --- Lectura de páginas ---------------------------------------------------
        # Solo para pruebas locales: permite leer http://127.0.0.1 (loopback); las redes privadas siguen bloqueadas.
        self.allow_private_hosts = _bool("TINKUY_ALLOW_PRIVATE_HOSTS", False)
        self.browser_fallback = _bool("TINKUY_BROWSER", True)
        self.max_page_bytes = int(os.getenv("TINKUY_MAX_PAGE_BYTES", str(8 * 1024 * 1024)))
        self.max_image_bytes = int(os.getenv("TINKUY_MAX_IMAGE_BYTES", str(6 * 1024 * 1024)))
        self.fetch_timeout = float(os.getenv("TINKUY_FETCH_TIMEOUT", "20"))
        self.user_agent = os.getenv(
            "TINKUY_USER_AGENT",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0 Safari/537.36 Tinkuy/1.0 (analisis academico de prensa)",
        )

        # --- Geocodificación --------------------------------------------------------
        # nominatim (con nomenclátor local de respaldo) | gazetteer (solo local) | off
        self.geocoding = os.getenv("TINKUY_GEOCODING", "nominatim").strip().lower()
        self.nominatim_url = os.getenv("TINKUY_NOMINATIM_URL", "https://nominatim.openstreetmap.org").rstrip("/")
        self.contact_email = os.getenv("TINKUY_CONTACT_EMAIL", "").strip()

        # --- Exportación --------------------------------------------------------------
        self.pdf_enabled = _bool("TINKUY_PDF", True)

    # Estado público (sin secretos) --------------------------------------------------
    def llm_status(self) -> dict:
        prov = self.llm_provider
        if prov == "anthropic":
            ok = bool(self.anthropic_api_key)
            return {"proveedor": "Anthropic", "modelo": self.anthropic_model, "configurado": ok,
                    "detalle": "" if ok else "Falta la variable de entorno ANTHROPIC_API_KEY."}
        if prov == "openai":
            ok = bool(self.openai_api_key)
            return {"proveedor": "Compatible con OpenAI", "modelo": self.openai_model, "configurado": ok,
                    "detalle": "" if ok else "Falta TINKUY_OPENAI_API_KEY (u OPENAI_API_KEY)."}
        if prov == "replay":
            ok = self.replay_dir.exists()
            return {"proveedor": "Respuestas pregrabadas (modo de prueba)", "modelo": "replay", "configurado": ok,
                    "detalle": "Modo de demostración: las respuestas del modelo se leen de archivos de prueba, no de un proveedor real."}
        return {"proveedor": "Ninguno", "modelo": "", "configurado": False,
                "detalle": "Análisis con modelo de lenguaje desactivado (TINKUY_LLM_PROVIDER=none)."}


settings = Settings()
