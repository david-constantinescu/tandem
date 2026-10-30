"""Code-level guards for the browser agent. None of these can be overridden by the model.

* Navigation is limited to the site's own domains (checked before every request and after redirects).
* robots.txt is honoured for real sites (user agent "TandemBrowserAgent").
* Password, card, CVV, IBAN, passport and one-time-code fields are never filled by the agent.
* CAPTCHA and bot-challenge pages (reCAPTCHA, hCaptcha, Cloudflare Turnstile, DataDome, PerimeterX,
  Akamai) stop the run; Tandem never tries to solve or bypass them.
* Login walls stop the run; Tandem does not sign in to third-party accounts.
"""
from __future__ import annotations

import re
import urllib.robotparser
from urllib.parse import urlparse

import httpx

from app.services.browser.sites import Site
from app.services.cache import cache_get, cache_set

AGENT_NAME = "TandemBrowserAgent"


class PolicyViolation(Exception):
    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.code = code


def host_allowed(site: Site, url: str) -> bool:
    parsed = urlparse(url)
    if site.simulated:
        return parsed.path.startswith("/" + site.domains[0] + "/") or parsed.path.rstrip("/") == "/" + site.domains[0]
    if not parsed.hostname:
        return False
    host = parsed.hostname.lower()
    if parsed.scheme != "https":
        from flask import current_app

        # Plain HTTP only for local fixture sites in the test suite.
        if not (current_app.config.get("TESTING") and host in ("127.0.0.1", "localhost") and parsed.scheme == "http"):
            return False
    return any(_brand_match(host, d[:-1]) if d.endswith(".") else (host == d or host.endswith("." + d))
               for d in site.domains)


def _brand_match(host: str, brand: str) -> bool:
    """brand.<country suffix> such as klm.ro or airfrance.co.uk; never brand.attacker.com."""
    labels = host.split(".")
    if brand not in labels:
        return False
    suffix = labels[labels.index(brand) + 1:]
    return 1 <= len(suffix) <= 2 and all(1 < len(x) <= 3 and x.isalpha() for x in suffix)


def check_navigation(site: Site, url: str) -> None:
    if not host_allowed(site, url):
        raise PolicyViolation(f"Navigation to {urlparse(url).hostname or url} is outside {site.name}", "off_site")
    if not site.simulated and not robots_allows(url):
        raise PolicyViolation(f"{site.name}'s robots.txt disallows automated access to this page", "robots_disallow")


def robots_allows(url: str) -> bool:
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    cached = cache_get("robots", base)
    if cached is None:
        try:
            resp = httpx.get(f"{base}/robots.txt", timeout=8, headers={"User-Agent": AGENT_NAME}, follow_redirects=True)
            text = resp.text if resp.status_code == 200 else ""
            status = resp.status_code
        except httpx.HTTPError:
            text, status = "", 0
        cached = {"text": text, "status": status}
        cache_set("robots", base, cached, ttl_hours=24)
    if cached["status"] in (401, 403):
        return False  # robots.txt itself forbidden: treat as disallow-all
    rp = urllib.robotparser.RobotFileParser()
    rp.parse(cached["text"].splitlines())
    return rp.can_fetch(AGENT_NAME, url)


_SENSITIVE_NAME = re.compile(
    r"pass(word|wd)|card.?(num|no)|cc.?(num|no)|credit|debit|cvv|cvc|csc|security.?code|expir|iban|swift|bic|"
    r"sort.?code|account.?num|routing|passport|national.?id|ssn|otp|one.?time|verification.?code|pin\b",
    re.I,
)
_SENSITIVE_AUTOCOMPLETE = re.compile(r"cc-|current-password|new-password|one-time-code", re.I)


def is_sensitive_field(el: dict) -> bool:
    if (el.get("type") or "").lower() in ("password",):
        return True
    if _SENSITIVE_AUTOCOMPLETE.search(el.get("autocomplete") or ""):
        return True
    text = " ".join(str(el.get(k) or "") for k in ("name", "id_attr", "label", "placeholder"))
    return bool(_SENSITIVE_NAME.search(text))


_CHALLENGE_MARKERS = (
    ("recaptcha", re.compile(r"google\.com/recaptcha|g-recaptcha|grecaptcha", re.I)),
    ("hcaptcha", re.compile(r"hcaptcha\.com|h-captcha", re.I)),
    ("turnstile", re.compile(r"challenges\.cloudflare\.com|cf-turnstile|cf-chl", re.I)),
    ("datadome", re.compile(r"captcha-delivery\.com|datadome", re.I)),
    ("perimeterx", re.compile(r"px-captcha|perimeterx|human\.com/challenge", re.I)),
    ("akamai", re.compile(r"pardon our interruption|_abck|akamai bot", re.I)),
    ("generic", re.compile(r"verify (that )?you are (a )?human|are you a robot|unusual traffic|just a moment\.\.\.|"
                           r"attention required|access denied|request blocked", re.I)),
)


def detect_challenge(html_or_text: str, frame_urls: list[str] | None = None) -> str | None:
    blob = (html_or_text or "")[:200_000] + " " + " ".join(frame_urls or [])
    for name, pattern in _CHALLENGE_MARKERS:
        if pattern.search(blob):
            return name
    return None


def detect_login_wall(elements: list[dict]) -> bool:
    return any((e.get("type") or "").lower() == "password" for e in elements)


def detect_payment_page(elements: list[dict]) -> bool:
    return any(_SENSITIVE_AUTOCOMPLETE.search(e.get("autocomplete") or "") and "password" not in (e.get("autocomplete") or "")
               or re.search(r"card.?(num|no)|cvv|cvc|expir", " ".join(str(e.get(k) or "") for k in ("name", "label", "id_attr")), re.I)
               for e in elements)


PERSONAL_FIELD = re.compile(r"first.?name|last.?name|surname|full.?name|given|family|e-?mail|phone|mobile|birth|"
                            r"date.?of.?birth|dob|address|passenger|traveller|traveler", re.I)


def is_personal_field(el: dict) -> bool:
    text = " ".join(str(el.get(k) or "") for k in ("name", "id_attr", "label", "placeholder", "autocomplete"))
    return bool(PERSONAL_FIELD.search(text))
