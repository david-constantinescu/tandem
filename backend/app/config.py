"""Application configuration.

All settings come from environment variables (see `.env.example`). `validate_config`
runs at startup and refuses to boot a production deployment with unsafe defaults.
"""
from __future__ import annotations

import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return int(raw) if raw not in (None, "") else default


def _str(name: str, default: str = "") -> str:
    raw = os.environ.get(name)
    return raw if raw not in (None, "") else default


def load_dotenv(path: Path | None = None) -> None:
    """Minimal .env loader (does not override variables already set)."""
    path = path or BACKEND_DIR / ".env"
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if value[:1] in ("'", '"') and value[:1] in value[1:]:
            value = value[1:value.index(value[0], 1)]
        else:
            value = value.split(" #", 1)[0].split("\t#", 1)[0].strip()
        os.environ.setdefault(key.strip(), value)


def normalise_database_url(url: str) -> str:
    """Accept provider-style URLs (postgres://, postgresql://) and select the psycopg 3 driver."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


class Config:
    def __init__(self) -> None:
        on_vercel = bool(os.environ.get("VERCEL"))
        self.ON_VERCEL = on_vercel
        self.APP_ENV = _str("APP_ENV", "development")
        self.SECRET_KEY = _str("SECRET_KEY", "dev-insecure-secret-change-me")
        self.ENCRYPTION_KEY = _str("ENCRYPTION_KEY")
        self.SQLALCHEMY_DATABASE_URI = normalise_database_url(_str(
            "DATABASE_URL", "postgresql+psycopg://tandem@127.0.0.1:5433/tandem"
        ))
        self.REDIS_URL = _str("REDIS_URL")
        self.FRONTEND_URL = _str("FRONTEND_URL", "http://localhost:5173")
        self.BACKEND_URL = _str("BACKEND_URL", "http://localhost:5050")
        self.FRONTEND_DIST = _str("FRONTEND_DIST", str(BACKEND_DIR.parent / "frontend" / "dist"))

        # Sessions
        self.SESSION_COOKIE_NAME = "tandem_session"
        self.SESSION_TTL_HOURS = _int("SESSION_TTL_HOURS", 24 * 14)
        self.SESSION_COOKIE_SECURE = _bool("SESSION_COOKIE_SECURE", self.APP_ENV == "production")

        # Storage
        # local | s3 | database (serverless hosts such as Vercel have no persistent filesystem)
        self.STORAGE_TYPE = _str("STORAGE_TYPE", "database" if on_vercel else "local")
        self.STORAGE_LOCAL_PATH = _str("STORAGE_LOCAL_PATH", str(BACKEND_DIR / "var" / "storage"))
        self.STORAGE_BUCKET = _str("STORAGE_BUCKET")
        self.STORAGE_ENDPOINT = _str("STORAGE_ENDPOINT")
        self.STORAGE_ACCESS_KEY = _str("STORAGE_ACCESS_KEY")
        self.STORAGE_SECRET_KEY = _str("STORAGE_SECRET_KEY")
        self.STORAGE_REGION = _str("STORAGE_REGION", "us-east-1")
        self.MAX_UPLOAD_BYTES = _int("MAX_UPLOAD_BYTES", 20 * 1024 * 1024)
        self.MAX_FILES_PER_UPLOAD = _int("MAX_FILES_PER_UPLOAD", 10)

        # Jobs
        self.JOB_RUNNER = _str("JOB_RUNNER", "inline" if on_vercel else "worker")  # worker | inline
        self.CRON_SECRET = _str("CRON_SECRET")
        self.WORKER_POLL_SECONDS = float(_str("WORKER_POLL_SECONDS", "1.0"))
        self.SCHEDULED_CHECK_MINUTES = _int("SCHEDULED_CHECK_MINUTES", 10)

        # AI
        self.AI_DEFAULT_PROVIDER = _str("AI_DEFAULT_PROVIDER", "gemini")
        self.AI_ALLOW_PAID_MODELS = _bool("AI_ALLOW_PAID_MODELS", False)
        self.AI_ENABLE_FALLBACK = _bool("AI_ENABLE_FALLBACK", True)
        self.AI_REQUEST_TIMEOUT = _int("AI_REQUEST_TIMEOUT", 90)
        self.AI_MAX_RETRIES = _int("AI_MAX_RETRIES", 2)
        self.AI_CACHE_TTL_HOURS = _int("AI_CACHE_TTL_HOURS", 24 * 7)

        self.GEMINI_API_KEY = _str("GEMINI_API_KEY")
        self.GEMINI_EXTRACTION_MODEL = _str("GEMINI_EXTRACTION_MODEL", "gemini-2.5-flash")
        self.GEMINI_REASONING_MODEL = _str("GEMINI_REASONING_MODEL", "gemini-2.5-flash")
        self.GEMINI_VISION_MODEL = _str("GEMINI_VISION_MODEL", "gemini-2.5-flash")
        self.GEMINI_FAST_MODEL = _str("GEMINI_FAST_MODEL", "gemini-2.5-flash-lite")
        # Tried in order when the main model is out of quota, at capacity or slow (free-tier limits are per model).
        self.GEMINI_FALLBACK_MODELS = _str("GEMINI_FALLBACK_MODELS", "gemini-3.5-flash-lite,gemini-2.5-flash-lite")
        self.GEMINI_EMBEDDING_MODEL = _str("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")

        self.ZAI_API_KEY = _str("ZAI_API_KEY")
        self.ZAI_BASE_URL = _str("ZAI_BASE_URL", "https://api.z.ai/api/paas/v4")
        self.ZAI_TEXT_MODEL = _str("ZAI_TEXT_MODEL", "glm-4.7-flash")
        self.ZAI_FAST_MODEL = _str("ZAI_FAST_MODEL", "glm-4.5-flash")
        self.ZAI_REASONING_MODEL = _str("ZAI_REASONING_MODEL", "glm-4.7-flash")
        self.ZAI_VISION_MODEL = _str("ZAI_VISION_MODEL", "glm-4.6v-flash")
        self.ZAI_DOCUMENT_MODEL = _str("ZAI_DOCUMENT_MODEL", "glm-5.3-flash")
        self.ZAI_IMAGE_DATA_URL = _bool("ZAI_IMAGE_DATA_URL", True)

        self.GROQ_API_KEY = _str("GROQ_API_KEY")
        self.GROQ_BASE_URL = _str("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
        self.GROQ_TEXT_MODEL = _str("GROQ_TEXT_MODEL", "openai/gpt-oss-20b")
        self.GROQ_REASONING_MODEL = _str("GROQ_REASONING_MODEL", "openai/gpt-oss-120b")

        # Google OAuth (Gmail, read-only)
        self.GOOGLE_CLIENT_ID = _str("GOOGLE_CLIENT_ID")
        self.GOOGLE_CLIENT_SECRET = _str("GOOGLE_CLIENT_SECRET")
        self.GOOGLE_REDIRECT_URI = _str(
            "GOOGLE_REDIRECT_URI", f"{self.BACKEND_URL}/api/v1/integrations/gmail/callback"
        )

        # Travel providers
        self.BOOKING_COM_AFFILIATE_ID = _str("BOOKING_COM_AFFILIATE_ID")
        self.BOOKING_COM_API_TOKEN = _str("BOOKING_COM_API_TOKEN")
        self.BOOKING_COM_ENV = _str("BOOKING_COM_ENV", "sandbox")
        self.BOOKING_COM_API_VERSION = _str("BOOKING_COM_API_VERSION", "3.3")
        self.EXPEDIA_API_KEY = _str("EXPEDIA_API_KEY")
        self.EXPEDIA_SHARED_SECRET = _str("EXPEDIA_SHARED_SECRET")
        self.EXPEDIA_ENV = _str("EXPEDIA_ENV", "test")
        self.EXPEDIA_ACTIVITIES_ENABLED = _bool("EXPEDIA_ACTIVITIES_ENABLED", False)
        self.VIATOR_API_KEY = _str("VIATOR_API_KEY")
        self.VIATOR_ENV = _str("VIATOR_ENV", "sandbox")
        self.GETYOURGUIDE_ACCESS_TOKEN = _str("GETYOURGUIDE_ACCESS_TOKEN")
        self.OSM_PLACES_ENABLED = _bool("OSM_PLACES_ENABLED", True)
        self.OVERPASS_URL = _str("OVERPASS_URL", "https://overpass-api.de/api/interpreter")

        # Live trip context: weather (Open-Meteo) and local news (Google News RSS, GDELT) need no keys.
        # TAVILY_API_KEY adds general web search for the assistant (free tier: 1,000 searches a month).
        self.WEATHER_ENABLED = _bool("WEATHER_ENABLED", True)
        self.OPEN_METEO_URL = _str("OPEN_METEO_URL", "https://api.open-meteo.com/v1/forecast")
        self.NEWS_ENABLED = _bool("NEWS_ENABLED", True)
        self.TAVILY_API_KEY = _str("TAVILY_API_KEY")

        # Browser agent (see docs/BROWSER_AGENT.md)
        self.BROWSER_ASSIST_SITES = _str("BROWSER_ASSIST_SITES")  # comma-separated site keys, after terms review
        self.BROWSER_WORKER_ENABLED = _bool("BROWSER_WORKER_ENABLED", False)  # Playwright installed in the worker
        self.BROWSER_CDP_URL = _str("BROWSER_CDP_URL")  # optional remote Chromium over CDP

        # Location services
        self.LOCATION_PROVIDER = _str("LOCATION_PROVIDER", "offline" if on_vercel else "nominatim")  # nominatim | offline
        self.NOMINATIM_URL = _str("NOMINATIM_URL", "https://nominatim.openstreetmap.org")
        self.OSM_CONTACT_EMAIL = _str("OSM_CONTACT_EMAIL")
        self.ROUTING_OSRM_URL = _str("ROUTING_OSRM_URL")
        self.MIN_TRANSFER_BUFFER_MINUTES = _int("MIN_TRANSFER_BUFFER_MINUTES", 30)
        self.AIRPORT_EXIT_BUFFER_MINUTES = _int("AIRPORT_EXIT_BUFFER_MINUTES", 60)

        # Demo
        self.DEMO_MODE = _bool("DEMO_MODE", False)
        self.DEMO_ACCOUNT_ENABLED = _bool("DEMO_ACCOUNT_ENABLED", True)
        self.DEMO_ACCOUNT_EMAIL = _str("DEMO_ACCOUNT_EMAIL", "demo@tandem.travel")
        self.DEMO_ACCOUNT_PASSWORD = _str("DEMO_ACCOUNT_PASSWORD")
        self.DEMO_ALLOW_EXTERNAL_AI = _bool("DEMO_ALLOW_EXTERNAL_AI", True)
        self.DEMO_SESSION_HOURS = _int("DEMO_SESSION_HOURS", 24)
        self.DEMO_DAILY_AI_REQUESTS = _int("DEMO_DAILY_AI_REQUESTS", 60)

        # Rate limiting
        self.RATELIMIT_STORAGE_URI = _str("RATELIMIT_STORAGE_URI", self.REDIS_URL or "memory://")
        self.RATELIMIT_ENABLED = _bool("RATELIMIT_ENABLED", True)
        self.DEMO_RATE_LIMIT = _str("DEMO_RATE_LIMIT", "120 per hour")
        # Number of reverse proxies in front of the app whose X-Forwarded-* headers are trusted.
        self.TRUSTED_PROXIES = _int("TRUSTED_PROXIES", 0)

        self.TESTING = False

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    def as_flask_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if k.isupper()}


class ConfigError(RuntimeError):
    pass


def validate_config(cfg: dict) -> list[str]:
    """Return warnings; raise ConfigError on fatal misconfiguration."""
    warnings: list[str] = []
    production = cfg.get("APP_ENV") == "production"
    if cfg["SECRET_KEY"].startswith("dev-insecure") or len(cfg["SECRET_KEY"]) < 32:
        if production:
            raise ConfigError("SECRET_KEY must be set to a random value of at least 32 characters in production")
        warnings.append("SECRET_KEY is a development default")
    if not cfg.get("ENCRYPTION_KEY"):
        if production:
            raise ConfigError("ENCRYPTION_KEY must be set in production (Fernet key, see docs/SECURITY.md)")
        warnings.append("ENCRYPTION_KEY not set; deriving a development key from SECRET_KEY")
    if not cfg.get("SQLALCHEMY_DATABASE_URI"):
        raise ConfigError("DATABASE_URL is required")
    if cfg.get("STORAGE_TYPE") == "s3" and not cfg.get("STORAGE_BUCKET"):
        raise ConfigError("STORAGE_BUCKET is required when STORAGE_TYPE=s3")
    if production and cfg.get("JOB_RUNNER") == "inline":
        warnings.append("JOB_RUNNER=inline in production processes jobs inside web requests")
    if production and not cfg.get("SESSION_COOKIE_SECURE"):
        raise ConfigError("SESSION_COOKIE_SECURE must be true in production")
    if cfg.get("LOCATION_PROVIDER") == "nominatim" and not cfg.get("OSM_CONTACT_EMAIL"):
        warnings.append("OSM_CONTACT_EMAIL not set; Nominatim/Overpass requests use a generic User-Agent")
    return warnings
