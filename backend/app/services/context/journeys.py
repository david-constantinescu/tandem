"""Real ways to get from A to B: prefilled journey planners plus the official operators for the country.

Tandem doesn't buy tickets on real websites (their terms rarely allow automated purchases and they sit behind
logins and CAPTCHAs). Instead it opens the right real page with the route filled in, where that page supports it,
and the user books there; the confirmation then comes back into Tandem.
"""
from __future__ import annotations

from urllib.parse import quote, urlencode

from app.services.browser.sites import REAL_SITES, handoff_url
from app.services.context.news import country_for

MODES = ("train", "bus", "flight")
EUROSTAR = {"GB", "FR", "BE", "NL"}
LOW_COST = {"ryanair", "easyjet", "wizzair"}  # fly between most European countries, whoever's home they are
EUROPE = {"IT", "FR", "ES", "DE", "AT", "PT", "RO", "NL", "GR", "GB", "IE", "BE", "CH", "CZ", "HU", "PL"}


def options(origin: str, destination: str, *, day: str | None = None, mode: str | None = None,
            country: str | None = None) -> dict:
    """Links for a journey. `mode` narrows the operators; planners cover every mode."""
    links = [{
        "kind": "planner", "name": "Google Maps",
        "url": "https://www.google.com/maps/dir/?" + urlencode({"api": 1, "origin": origin, "destination": destination,
                                                                "travelmode": "transit"}),
        "covers": "train, bus, metro — live timetables and delays",
    }]
    if mode in (None, "flight"):
        q = f"Flights from {origin} to {destination}" + (f" on {day}" if day else "")
        links.append({"kind": "planner", "name": "Google Flights",
                      "url": f"https://www.google.com/travel/flights?q={quote(q)}", "covers": "flights, all airlines"})
    oc, dc = country_for(origin), country_for(destination)
    code = oc or dc or (country or "").upper() or None
    # Abroad, a country's own buses and trains rarely help: its airlines, both ends' airlines, and the
    # Europe-wide sellers do.
    abroad = {oc, dc} if oc and dc and oc != dc else None
    params = {"origin": origin, "destination": destination, "date": day or ""}
    for site in REAL_SITES:
        if site.category not in MODES or (mode and site.category != mode):
            continue
        if site.key == "eurostar" and not ({oc or code, dc or code} <= EUROSTAR):
            continue
        if abroad:
            keep = site.country == "EU" or (site.category == "flight" and (site.country in abroad or
                                                                           (site.key in LOW_COST and abroad <= EUROPE)))
        else:
            keep = site.country in (code, "EU") or (code is None and site.country == "EU")
        if keep:
            links.append({"kind": "operator", "name": site.name, "url": handoff_url(site, params), "covers": site.category,
                          "official": site.country != "EU", "automation_forbidden": site.automation_forbidden,
                          "local": site.country in (oc, dc, code) or site.key == "eurostar"})
    # Planners, then the operators of the places themselves, then everyone else.
    links.sort(key=lambda link: (link["kind"] != "planner", not link.get("local", True), not link.get("official", True)))
    return {"origin": origin, "destination": destination, "date": day, "country": code, "links": links[:9],
            "note": "Real websites: you book there; forward the confirmation to Tandem and it joins your trip."}
