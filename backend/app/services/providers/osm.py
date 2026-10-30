"""OpenStreetMap places (Overpass API): a real, keyless discovery source.

Search only. OSM lists places (museums, galleries, monuments, viewpoints, attractions); it has no
tickets, prices or availability, and its opening_hours tags are community data, not verified.
Results are labelled accordingly and cached to respect the public Overpass instance's usage policy.
"""
from __future__ import annotations

import logging

import httpx

from app.services import geo
from app.services.cache import cache_get, cache_set
from app.services.providers.base import (
    DISABLED, SEARCH_ONLY, TEMPORARILY_UNAVAILABLE, ActivityResult, ActivitySearchRequest, ProviderRequestError,
    TravelProviderAdapter,
)

log = logging.getLogger("tandem.providers.osm")

CATEGORY_TAGS = {
    "museums": ['tourism="museum"', 'tourism="gallery"'],
    "historical": ['historic~"monument|castle|ruins|archaeological_site|memorial"'],
    "architecture": ['historic="building"', 'building="cathedral"', 'amenity="place_of_worship"]["tourism"="attraction"'],
    "outdoor": ['leisure="park"]["name"', 'tourism="viewpoint"'],
    "entertainment": ['amenity="theatre"', 'tourism="theme_park"', 'tourism="zoo"'],
    "attractions": ['tourism="attraction"'],
}
DEFAULT_CATEGORIES = ["museums", "attractions", "historical"]


class OSMPlacesAdapter(TravelProviderAdapter):
    key = "osm"
    name = "OpenStreetMap places"
    docs_url = "https://wiki.openstreetmap.org/wiki/Overpass_API"

    def state(self) -> str:
        if not self.cfg.get("OSM_PLACES_ENABLED", True):
            return DISABLED
        return SEARCH_ONLY

    def capabilities(self) -> dict:
        caps = super().capabilities()
        caps.update(search=True, details=False, availability=False, booking=False, redirect=True,
                    environment="production",
                    notes=["Public place listings from OpenStreetMap. No prices, tickets or availability.",
                           "Opening hours are community-maintained and shown as unverified.",
                           "Data © OpenStreetMap contributors, ODbL."])
        return caps

    def search(self, req: ActivitySearchRequest) -> list[ActivityResult]:
        if self.state() == DISABLED:
            return []
        lat, lon = req.lat, req.lon
        if lat is None and req.location:
            place = geo.resolve_place(req.location)
            if place:
                lat, lon = place.lat, place.lon
        if lat is None:
            raise ProviderRequestError("A location is needed to search OpenStreetMap", code="location_required")
        cats = [c for c in (req.categories or DEFAULT_CATEGORIES) if c in CATEGORY_TAGS] or DEFAULT_CATEGORIES
        radius = int(min(max(req.radius_km, 0.5), 10) * 1000)
        cache_key = {"lat": round(lat, 3), "lon": round(lon, 3), "r": radius, "c": sorted(cats)}
        rows = cache_get("osm_places", cache_key)
        if rows is None:
            rows = self._query(lat, lon, radius, cats)
            cache_set("osm_places", cache_key, rows, ttl_hours=24)
        results = []
        q = (req.query or "").lower()
        for el in rows:
            tags = el.get("tags", {})
            name = tags.get("name:en") or tags.get("name")
            if not name or (q and q not in name.lower()):
                continue
            elat = el.get("lat") or (el.get("center") or {}).get("lat")
            elon = el.get("lon") or (el.get("center") or {}).get("lon")
            if req.accessible_only and tags.get("wheelchair") not in ("yes", "designated"):
                continue
            results.append(ActivityResult(
                provider=self.key, provider_item_id=f"{el['type']}/{el['id']}", title=name,
                description=_describe(tags), location_name=name, address=_address(tags), lat=elat, lon=elon,
                price=0.0 if tags.get("fee") == "no" else None, currency=None,
                price_basis="free" if tags.get("fee") == "no" else None, categories=_categories(tags),
                booking_url=tags.get("website") or tags.get("contact:website"),
                accessible={"yes": True, "designated": True, "no": False}.get(tags.get("wheelchair")),
                opening_hours_text=tags.get("opening_hours"), availability_checked=False,
                source_label="OpenStreetMap listing — availability and prices unknown",
                attribution="© OpenStreetMap contributors",
            ))
        return results[: req.limit]

    def _query(self, lat: float, lon: float, radius: int, cats: list[str]) -> list[dict]:
        selectors = []
        for cat in cats:
            for tag in CATEGORY_TAGS[cat]:
                selectors.append(f'nwr[{tag}](around:{radius},{lat},{lon});')
        query = f"[out:json][timeout:20];({''.join(selectors)});out center tags 60;"
        try:
            resp = httpx.post(self.cfg["OVERPASS_URL"], data={"data": query}, timeout=25,
                              headers={"User-Agent": geo.user_agent()})
        except httpx.HTTPError as exc:
            raise ProviderRequestError(f"OpenStreetMap is unreachable ({type(exc).__name__})",
                                       code=TEMPORARILY_UNAVAILABLE, retryable=True) from exc
        if resp.status_code in (429, 504):
            raise ProviderRequestError("OpenStreetMap is busy; try again shortly", code=TEMPORARILY_UNAVAILABLE,
                                       retryable=True)
        if resp.status_code != 200:
            raise ProviderRequestError(f"OpenStreetMap returned HTTP {resp.status_code}", code="provider_error")
        return resp.json().get("elements", [])


def _describe(tags: dict) -> str:
    bits = []
    for key in ("tourism", "historic", "amenity", "leisure"):
        if tags.get(key):
            bits.append(tags[key].replace("_", " "))
    if tags.get("description"):
        bits.append(tags["description"][:200])
    return " · ".join(bits).capitalize()


def _address(tags: dict) -> str | None:
    street = " ".join(x for x in (tags.get("addr:street"), tags.get("addr:housenumber")) if x)
    parts = [p for p in (street, tags.get("addr:postcode"), tags.get("addr:city")) if p]
    return ", ".join(parts) or None


def _categories(tags: dict) -> list[str]:
    cats = []
    if tags.get("tourism") in ("museum", "gallery"):
        cats.append("museums")
    if tags.get("historic"):
        cats.append("historical")
    if tags.get("tourism") == "viewpoint" or tags.get("leisure") == "park":
        cats.append("outdoor")
    if tags.get("tourism") == "attraction":
        cats.append("attractions")
    return cats or ["attractions"]
