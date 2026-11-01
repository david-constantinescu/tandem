"""providerii parteneri (booking.com, expedia, viator, getyourguide). merg doar cu chei de partener"""
from __future__ import annotations

import hashlib
import logging
import time

import httpx

from app.services import geo
from app.services.cache import cache_get, cache_set
from app.services.providers.base import (
    AWAITING_PARTNER_APPROVAL, REDIRECT_ONLY, SANDBOX_ONLY, SEARCH_ONLY, ActivityResult, ActivitySearchRequest,
    ProviderRequestError, TravelProviderAdapter,
)

log = logging.getLogger("tandem.providers")


def _http(method: str, url: str, provider: str, **kwargs) -> dict:
    try:
        resp = httpx.request(method, url, timeout=20, **kwargs)
    except httpx.HTTPError as exc:
        raise ProviderRequestError(f"{provider} is unreachable ({type(exc).__name__})", code="temporarily_unavailable",
                                   retryable=True) from exc
    if resp.status_code == 429:
        raise ProviderRequestError(f"{provider} rate limit reached", code="rate_limited", retryable=True)
    if resp.status_code in (401, 403):
        raise ProviderRequestError(f"{provider} rejected the credentials ({resp.status_code})", code="unauthorised")
    if resp.status_code >= 400:
        raise ProviderRequestError(f"{provider} returned HTTP {resp.status_code}", code="provider_error",
                                   retryable=resp.status_code >= 500)
    try:
        return resp.json()
    except ValueError as exc:
        raise ProviderRequestError(f"{provider} returned an unreadable response", code="provider_error") from exc


class BookingComAdapter(TravelProviderAdapter):
    """Booking.com Demand API - Attractions (early-access pilot)"""

    key = "booking_com"
    name = "Booking.com Attractions"
    docs_url = "https://developers.booking.com/demand/docs/attractions/attractions-quick-guide"

    def _configured(self) -> bool:
        return bool(self.cfg.get("BOOKING_COM_API_TOKEN") and self.cfg.get("BOOKING_COM_AFFILIATE_ID"))

    def state(self) -> str:
        if not self._configured():
            return AWAITING_PARTNER_APPROVAL
        return SANDBOX_ONLY if self.cfg.get("BOOKING_COM_ENV") == "sandbox" else REDIRECT_ONLY

    def capabilities(self) -> dict:
        caps = super().capabilities()
        ok = self._configured()
        caps.update(search=ok, details=ok, availability=False, booking=False, redirect=ok,
                    environment=self.cfg.get("BOOKING_COM_ENV"),
                    notes=["Attractions API is an early-access pilot for selected Booking.com affiliate partners; "
                           "access is granted by a Booking.com account manager.",
                           "Search returns prices and free-cancellation flags; booking happens on Booking.com "
                           "(redirect with affiliate id).",
                           "Untested against live credentials in this build."])
        return caps

    def _base(self) -> str:
        host = "demandapi-sandbox.booking.com" if self.cfg.get("BOOKING_COM_ENV") == "sandbox" else "demandapi.booking.com"
        version = self.cfg.get("BOOKING_COM_API_VERSION", "3.3")
        return f"https://{host}/{version}" + ("/Beta" if version == "3.2" else "")

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.cfg['BOOKING_COM_API_TOKEN']}",
                "X-Affiliate-Id": str(self.cfg["BOOKING_COM_AFFILIATE_ID"]), "Content-Type": "application/json"}

    def _city_id(self, name: str, country: str | None) -> int | None:
        cached = cache_get("booking_city", f"{name}|{country}")
        if cached:
            return cached.get("id")
        body = {"languages": ["en-gb"], "rows": 1000}
        if country:
            body["country"] = country.lower()
        data = _http("POST", f"{self._base()}/common/locations/cities", self.name, json=body, headers=self._headers())
        for row in data.get("data", []):
            names = row.get("name") or {}
            label = names.get("en-gb") if isinstance(names, dict) else names
            if label and label.lower() == name.lower():
                cache_set("booking_city", f"{name}|{country}", {"id": row.get("id")}, ttl_hours=24 * 30)
                return row.get("id")
        return None

    def search(self, req: ActivitySearchRequest) -> list[ActivityResult]:
        if not self._configured():
            return super().search(req)
        place = geo.resolve_place(req.location or "", allow_network=True) if req.location else None
        city_id = self._city_id(place.city if place and place.city else (req.location or ""),
                                place.country if place else None)
        if city_id is None:
            raise ProviderRequestError("Booking.com does not recognise this city", code="location_unknown")
        body: dict = {"currency": req.currency, "cities": [city_id], "rows": min(req.limit, 50),
                      "sort": {"by": "most_popular"}}
        if req.date_from:
            body["dates"] = {"start_date": req.date_from.isoformat(),
                             "end_date": (req.date_to or req.date_from).isoformat()}
        data = _http("POST", f"{self._base()}/attractions/search", self.name, json=body, headers=self._headers())
        ids = [row["id"] for row in data.get("data", []) if row.get("id")]
        details = {}
        if ids:
            det = _http("POST", f"{self._base()}/attractions/details", self.name,
                        json={"attractions": ids[:100], "languages": ["en-gb"]}, headers=self._headers())
            details = {d["id"]: d for d in det.get("data", [])}
        results = []
        for row in data.get("data", []):
            d = details.get(row["id"], {})
            loc = (d.get("locations") or [{}])[0]
            coords = loc.get("coordinates") or {}
            price = row.get("price") or {}
            results.append(ActivityResult(
                provider=self.key, provider_item_id=row["id"], title=d.get("name") or row["id"],
                description=(d.get("long_description") or "")[:500], city=loc.get("city"), address=loc.get("address"),
                lat=coords.get("latitude"), lon=coords.get("longitude"), price=price.get("total"),
                currency=price.get("currency"), price_basis="from", categories=d.get("categories") or [],
                rating=(d.get("ratings") or {}).get("score"),
                review_count=(d.get("ratings") or {}).get("number_of_reviews"),
                booking_url=((row.get("urls") or {}).get("web") or {}).get("detail"),
                cancellation_policy="Free cancellation available" if row.get("free_cancellation") else None,
                availability_checked=False, bookable_via_api=False,
                source_label="Booking.com (prices from search; book on Booking.com)",
            ))
        return results


class ExpediaAdapter(TravelProviderAdapter):
    """Expedia Rapid. Activities is an early-access beta (OAuth 2.0; booking requires the Payments API). The
    lodging/common Rapid APIs use the documented EAN APIKey signature, implemented in `signature()`. Activities
    endpoints are not yet in the public API Explorer, so search is not enabled until beta access and endpoint
    documentation are available."""

    key = "expedia"
    name = "Expedia Rapid Activities"
    docs_url = "https://developers.expediagroup.com/rapid/activities"

    def state(self) -> str:
        if not (self.cfg.get("EXPEDIA_API_KEY") and self.cfg.get("EXPEDIA_SHARED_SECRET")):
            return AWAITING_PARTNER_APPROVAL
        if not self.cfg.get("EXPEDIA_ACTIVITIES_ENABLED"):
            return AWAITING_PARTNER_APPROVAL
        return SANDBOX_ONLY if self.cfg.get("EXPEDIA_ENV") == "test" else SEARCH_ONLY

    def capabilities(self) -> dict:
        caps = super().capabilities()
        caps.update(environment=self.cfg.get("EXPEDIA_ENV"),
                    notes=["Rapid Activities is in early access for selected partners (beta from Q3 2026, general "
                           "availability planned for 2027).",
                           "Activities search will be enabled once beta access and endpoint references are issued.",
                           "Booking would additionally require the Rapid Payments API token flow."])
        return caps

    def signature(self, timestamp: int | None = None) -> str:
        ts = timestamp or int(time.time())
        raw = f"{self.cfg['EXPEDIA_API_KEY']}{self.cfg['EXPEDIA_SHARED_SECRET']}{ts}"
        sig = hashlib.sha512(raw.encode()).hexdigest()
        return f"EAN APIKey={self.cfg['EXPEDIA_API_KEY']},Signature={sig},timestamp={ts}"

    def search(self, req: ActivitySearchRequest) -> list[ActivityResult]:
        if self.state() == AWAITING_PARTNER_APPROVAL:
            return super().search(req)
        raise ProviderRequestError(
            "Expedia Rapid Activities endpoints are not available to this account yet (beta access pending)",
            code="awaiting_partner_approval")


class ViatorAdapter(TravelProviderAdapter):
    """Viator Partner API v2 (affiliate)"""

    key = "viator"
    name = "Viator"
    docs_url = "https://docs.viator.com/partner-api/technical/"

    def state(self) -> str:
        if not self.cfg.get("VIATOR_API_KEY"):
            return AWAITING_PARTNER_APPROVAL
        return SANDBOX_ONLY if self.cfg.get("VIATOR_ENV") == "sandbox" else REDIRECT_ONLY

    def capabilities(self) -> dict:
        caps = super().capabilities()
        ok = bool(self.cfg.get("VIATOR_API_KEY"))
        caps.update(search=ok, details=ok, availability=False, booking=False, redirect=ok,
                    environment=self.cfg.get("VIATOR_ENV"),
                    notes=["Requires a Viator affiliate partner API key.",
                           "Results link to Viator for booking; in-app booking needs merchant access.",
                           "Endpoint paths must be validated with a sandbox key before production use."])
        return caps

    def _base(self) -> str:
        return ("https://api.sandbox.viator.com/partner" if self.cfg.get("VIATOR_ENV") == "sandbox"
                else "https://api.viator.com/partner")

    def _headers(self) -> dict:
        return {"exp-api-key": self.cfg["VIATOR_API_KEY"], "Accept": "application/json;version=2.0",
                "Accept-Language": "en-US", "Content-Type": "application/json"}

    def search(self, req: ActivitySearchRequest) -> list[ActivityResult]:
        if not self.cfg.get("VIATOR_API_KEY"):
            return super().search(req)
        body = {"searchTerm": " ".join(x for x in (req.query, req.location) if x) or "things to do",
                "searchTypes": [{"searchType": "PRODUCTS", "pagination": {"start": 1, "count": min(req.limit, 30)}}],
                "currency": req.currency}
        if req.date_from:
            body["productFiltering"] = {"dateRange": {"from": req.date_from.isoformat(),
                                                      "to": (req.date_to or req.date_from).isoformat()}}
        data = _http("POST", f"{self._base()}/search/freetext", self.name, json=body, headers=self._headers())
        results = []
        for p in ((data.get("products") or {}).get("results") or []):
            pricing = (p.get("pricing") or {}).get("summary") or {}
            images = p.get("images") or []
            variants = (images[0].get("variants") if images else None) or []
            results.append(ActivityResult(
                provider=self.key, provider_item_id=p.get("productCode", ""), title=p.get("title", ""),
                description=(p.get("description") or "")[:500],
                image_url=variants[-1].get("url") if variants else None,
                price=pricing.get("fromPrice"), currency=(p.get("pricing") or {}).get("currency"), price_basis="from",
                duration_minutes=((p.get("duration") or {}).get("fixedDurationInMinutes")),
                rating=((p.get("reviews") or {}).get("combinedAverageRating")),
                review_count=((p.get("reviews") or {}).get("totalReviews")), booking_url=p.get("productUrl"),
                availability_checked=False, bookable_via_api=False, source_label="Viator (book on Viator)",
            ))
        return results


class GetYourGuideAdapter(TravelProviderAdapter):
    key = "getyourguide"
    name = "GetYourGuide"
    docs_url = "https://partner.getyourguide.com/"

    def state(self) -> str:
        return AWAITING_PARTNER_APPROVAL if not self.cfg.get("GETYOURGUIDE_ACCESS_TOKEN") else SEARCH_ONLY

    def capabilities(self) -> dict:
        caps = super().capabilities()
        ok = bool(self.cfg.get("GETYOURGUIDE_ACCESS_TOKEN"))
        caps.update(search=ok, redirect=ok,
                    notes=["The GetYourGuide Partner API is available to approved partners only.",
                           "Search and link-out only in this build."])
        return caps

    def search(self, req: ActivitySearchRequest) -> list[ActivityResult]:
        if not self.cfg.get("GETYOURGUIDE_ACCESS_TOKEN"):
            return super().search(req)
        params = {"q": " ".join(x for x in (req.query, req.location) if x), "cnt_language": "en",
                  "currency": req.currency, "limit": min(req.limit, 30)}
        data = _http("GET", "https://api.getyourguide.com/1/tours", self.name, params=params,
                     headers={"X-ACCESS-TOKEN": self.cfg["GETYOURGUIDE_ACCESS_TOKEN"], "Accept": "application/json"})
        results = []
        for t in ((data.get("data") or {}).get("tours") or []):
            price = ((t.get("price") or {}).get("values") or {})
            results.append(ActivityResult(
                provider=self.key, provider_item_id=str(t.get("tour_id")), title=t.get("title", ""),
                description=(t.get("abstract") or "")[:500], price=price.get("amount"),
                currency=(t.get("price") or {}).get("currency") or req.currency, price_basis="from",
                rating=t.get("overall_rating"), review_count=t.get("number_of_ratings"), booking_url=t.get("url"),
                availability_checked=False, source_label="GetYourGuide (book on GetYourGuide)",
            ))
        return results


class _PartnerStub(TravelProviderAdapter):
    """activity marketplaces with partner-only APIs"""

    env_key = ""
    access_note = ""

    def state(self) -> str:
        return AWAITING_PARTNER_APPROVAL

    def capabilities(self) -> dict:
        caps = super().capabilities()
        caps.update(notes=[self.access_note, "Not implemented yet: needs partner credentials and API documentation."])
        return caps


class TiqetsAdapter(_PartnerStub):
    key, name, docs_url = "tiqets", "Tiqets", "https://www.tiqets.com/en/affiliate/"
    access_note = "Tiqets offers museum and attraction tickets through its affiliate and distribution partner programmes."


class KlookAdapter(_PartnerStub):
    key, name, docs_url = "klook", "Klook", "https://affiliate.klook.com/"
    access_note = "Klook's API is available to approved affiliate/distribution partners."


class HeadoutAdapter(_PartnerStub):
    key, name, docs_url = "headout", "Headout", "https://www.headout.com/affiliates/"
    access_note = "Headout's partner API requires an approved affiliate or distribution agreement."
