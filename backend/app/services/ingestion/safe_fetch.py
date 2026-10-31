"""descarcare de linkuri protejata impotriva ssrf (doar adrese publice, si la redirecturi)"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import httpx

from app.utils.errors import ValidationFailed

MAX_BYTES = 5 * 1024 * 1024
MAX_REDIRECTS = 3
ALLOWED_TYPES = ("text/html", "text/plain", "application/pdf", "image/jpeg", "image/png", "image/webp")


def _check_host(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValidationFailed("Only http and https links are supported", code="unsupported_url")
    if not parsed.hostname:
        raise ValidationFailed("The link has no host", code="unsupported_url")
    if parsed.port not in (None, 80, 443):
        raise ValidationFailed("Links on non-standard ports are not fetched", code="unsupported_url")
    if parsed.username or parsed.password:
        raise ValidationFailed("Links with embedded credentials are not fetched", code="unsupported_url")
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise ValidationFailed("The link's host could not be resolved", code="unresolvable_host") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved
                or ip.is_unspecified or (ip.version == 6 and ip.ipv4_mapped and not ip.ipv4_mapped.is_global)
                or not ip.is_global):
            raise ValidationFailed("Links to private or internal addresses are not allowed", code="blocked_address")


def fetch(url: str, *, user_agent: str) -> tuple[bytes, str, str]:
    """return (content, content_type, final_url)"""
    current = url.strip()
    with httpx.Client(follow_redirects=False, timeout=httpx.Timeout(10.0, connect=5.0),
                      headers={"User-Agent": user_agent, "Accept": ",".join(ALLOWED_TYPES)}) as client:
        for _ in range(MAX_REDIRECTS + 1):
            _check_host(current)
            try:
                with client.stream("GET", current) as resp:
                    if resp.status_code in (301, 302, 303, 307, 308):
                        location = resp.headers.get("location")
                        if not location:
                            raise ValidationFailed("Redirect without a location", code="fetch_failed")
                        current = urljoin(current, location)
                        continue
                    if resp.status_code != 200:
                        raise ValidationFailed(f"The page returned HTTP {resp.status_code}", code="fetch_failed")
                    ctype = resp.headers.get("content-type", "").split(";")[0].strip().lower()
                    if ctype not in ALLOWED_TYPES:
                        raise ValidationFailed(f"Unsupported content type {ctype or 'unknown'}", code="unsupported_type")
                    chunks, total = [], 0
                    for chunk in resp.iter_bytes():
                        total += len(chunk)
                        if total > MAX_BYTES:
                            raise ValidationFailed("The page is too large to import", code="file_too_large")
                        chunks.append(chunk)
                    return b"".join(chunks), ctype, current
            except httpx.HTTPError as exc:
                raise ValidationFailed(f"Could not fetch the link ({type(exc).__name__})", code="fetch_failed") from exc
    raise ValidationFailed("Too many redirects", code="fetch_failed")
