"""Ce modele Gemini folosim: le alegem singuri din lista Google, nu le scriem de mana in config.

Regula e simpla: cel mai nou "Flash" stabil e cel mai bun raport calitate/pret (Pro e scump, Flash-Lite e mai slab
dar mai ieftin si mai rapid). Previews, TTS, imagini si "omni" nu ne intereseaza. Lista se cere o data la 12 ore si
se tine in cache. Daca Google nu raspunde, mergem pe modelele 2.5, care sigur exista.
"""
from __future__ import annotations

import logging
import re

import httpx

log = logging.getLogger("tandem.ai.gemini")

MODELS_URL = "https://generativelanguage.googleapis.com/v1beta/models"
PATTERN = re.compile(r"^gemini-(\d+(?:\.\d+)?)-flash(-lite)?$")  # gemini-3.7-flash, gemini-3.5-flash-lite
FALLBACK = ["gemini-2.5-flash", "gemini-2.5-flash-lite"]


def _version(name: str) -> tuple[float, int]:
    m = PATTERN.match(name)
    return (float(m.group(1)), 0) if m else (0.0, 0)


def available(cfg) -> list[str]:
    """flash and Flash-Lite models this key can call, newest first"""
    from app.services.cache import cache_get, cache_set

    key = cfg.get("GEMINI_API_KEY") or ""
    if not key:
        return list(FALLBACK)
    try:
        cached = cache_get("gemini_models", "v1")
    except Exception:  # noqa: BLE001 - fara baza de date (scripturi), mergem direct la Google
        cached = None
    if cached:
        return cached
    try:
        resp = httpx.get(MODELS_URL, params={"pageSize": 300}, headers={"x-goog-api-key": key}, timeout=8)
        resp.raise_for_status()
        names = [m["name"].split("/", 1)[1] for m in resp.json().get("models", [])
                 if "generateContent" in m.get("supportedGenerationMethods", [])]
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        log.warning("gemini: could not list models (%s); using %s", type(exc).__name__, FALLBACK)
        return list(FALLBACK)
    found = sorted((n for n in names if PATTERN.match(n)), key=_version, reverse=True) or list(FALLBACK)
    try:
        cache_set("gemini_models", "v1", found, ttl_hours=12)
    except Exception:  # noqa: BLE001
        pass
    return found


def chain(cfg, role: str = "reasoning") -> list[str]:
    """best first. For the chat: the newest Flash models, then Flash-Lite as a cheap safety net. For quick jobs
    (sorting, short summaries): Flash-Lite first."""
    models = available(cfg)
    flash = [m for m in models if not m.endswith("-lite")]
    lite = [m for m in models if m.endswith("-lite")]
    if role == "fast":
        return (lite[:2] + flash[:2]) or list(FALLBACK)
    return (flash[:4] + lite[:2]) or list(FALLBACK)
