"""Registry of booking websites the browser agent knows about.

Policy (enforced in code, see policy.py):
  * Every real site defaults to **link_only**: Tandem opens the official site (or a verified deep link) for
    you and does not automate it. Terms of service have not been reviewed for automated access, and some
    sites (e.g. Ryanair) prohibit it outright.
  * An operator can enable **assisted** search for specific real sites with BROWSER_ASSIST_SITES after
    reviewing their terms. Assisted runs still obey robots.txt, a domain allow-list, CAPTCHA/MFA stops,
    and stop before personal-data and payment pages (hand-off to the user).
  * **Simulated** sites are Tandem's own demo websites (served at /demo-sites/...). They demonstrate a full
    agentic purchase with nothing real booked or charged.

Deep-link templates are only listed where they were opened and checked; others link to the homepage.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from urllib.parse import quote

from flask import current_app

CATEGORIES = ("train", "bus", "flight", "museum", "gallery", "attraction")


@dataclass(frozen=True)
class Site:
    key: str
    name: str
    category: str
    homepage: str
    domains: tuple[str, ...]  # "brand." = that brand on any country domain (brand.ro, brand.co.uk)
    country: str = ""
    simulated: bool = False
    terms_note: str = "Terms of service not reviewed for automated access; link only by default."
    automation_forbidden: bool = False
    deep_link: str | None = None  # format string with {origin},{destination},{date},{adults}
    deep_link_params: tuple[str, ...] = ()
    deep_link_checked: str | None = None  # date the template was opened and confirmed
    search_fields: tuple[str, ...] = ("origin", "destination", "date", "adults")
    notes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["policy"] = policy_for(self)
        d["agent_can"] = agent_capabilities(self)
        return d


def _real(key, name, category, homepage, domains, country="", **kw) -> Site:
    return Site(key=key, name=name, category=category, homepage=homepage, domains=tuple(domains), country=country, **kw)


REAL_SITES: tuple[Site, ...] = (
    # Trains
    _real("trenitalia", "Trenitalia", "train", "https://www.trenitalia.com/en.html", ["trenitalia.com", "lefrecce.it"], "IT"),
    _real("italo", "Italo", "train", "https://www.italotreno.com/en", ["italotreno.com", "italotreno.it"], "IT"),
    _real("sncf", "SNCF Connect", "train", "https://www.sncf-connect.com/en-en/", ["sncf-connect.com"], "FR"),
    _real("db", "Deutsche Bahn", "train", "https://int.bahn.de/en", ["bahn.de", "int.bahn.de"], "DE"),
    _real("eurostar", "Eurostar", "train", "https://www.eurostar.com/", ["eurostar.com"], "EU"),
    _real("renfe", "Renfe", "train", "https://www.renfe.com/es/en", ["renfe.com"], "ES"),
    _real("obb", "ÖBB", "train", "https://www.oebb.at/en/", ["oebb.at", "shop.oebbtickets.at"], "AT"),
    _real("sbb", "SBB", "train", "https://www.sbb.ch/en", ["sbb.ch"], "CH"),
    _real("cfr", "CFR Călători", "train", "https://bilete.cfrcalatori.ro/en-GB", ["cfrcalatori.ro"], "RO"),
    _real("trainline", "Trainline", "train", "https://www.thetrainline.com/", ["thetrainline.com"], "EU"),
    _real("omio", "Omio", "train", "https://www.omio.com/", ["omio.com"], "EU",
          notes=("Also sells buses and flights.",)),
    # Buses
    _real("flixbus", "FlixBus", "bus", "https://global.flixbus.com/", ["flixbus.com"], "EU"),
    _real("blablacar", "BlaBlaCar Bus", "bus", "https://www.blablacar.com/bus", ["blablacar.com"], "EU"),
    _real("nationalexpress", "National Express", "bus", "https://www.nationalexpress.com/", ["nationalexpress.com"], "GB"),
    _real("megabus", "Megabus", "bus", "https://uk.megabus.com/", ["megabus.com", "megabus.co.uk"], "GB"),
    _real("alsa", "ALSA", "bus", "https://www.alsa.com/en/", ["alsa.com"], "ES"),
    _real("regiojet", "RegioJet", "bus", "https://regiojet.com/", ["regiojet.com"], "CZ", notes=("Also runs trains.",)),
    # Flights
    _real("ryanair", "Ryanair", "flight", "https://www.ryanair.com/", ["ryanair.com"], "IE", automation_forbidden=True,
          terms_note="Ryanair's website terms prohibit automated access and screen scraping; link only."),
    _real("wizzair", "Wizz Air", "flight", "https://wizzair.com/", ["wizzair.com"], "HU"),
    _real("easyjet", "easyJet", "flight", "https://www.easyjet.com/en", ["easyjet.com"], "GB"),
    _real("tarom", "TAROM", "flight", "https://www.tarom.ro/en", ["tarom.ro"], "RO"),
    _real("lufthansa", "Lufthansa", "flight", "https://www.lufthansa.com/", ["lufthansa.com"], "DE"),
    _real("britishairways", "British Airways", "flight", "https://www.britishairways.com/", ["britishairways.com"], "GB"),
    _real("airfrance", "Air France", "flight", "https://wwws.airfrance.fr/", ["airfrance."], "FR",
          notes=("Redirects to your country's site (e.g. airfrance.ro).",)),
    _real("klm", "KLM", "flight", "https://www.klm.com/", ["klm."], "NL",
          notes=("Redirects to your country's site (e.g. klm.ro).",)),
    _real("ita", "ITA Airways", "flight", "https://www.ita-airways.com/", ["ita-airways.com"], "IT"),
    _real("aa", "American Airlines", "flight", "https://www.aa.com/", ["aa.com"], "US"),
    # Museums and galleries
    _real("vatican", "Vatican Museums", "museum", "https://tickets.museivaticani.va/home", ["museivaticani.va"], "VA"),
    _real("colosseum", "Colosseum (Parco archeologico)", "attraction", "https://ticketing.colosseo.it/en/",
          ["colosseo.it"], "IT"),
    _real("uffizi", "Uffizi Galleries", "gallery", "https://www.uffizi.it/en/tickets", ["uffizi.it", "b-ticket.com"], "IT"),
    _real("louvre", "Musée du Louvre", "museum", "https://www.ticketlouvre.fr/", ["louvre.fr", "ticketlouvre.fr"], "FR"),
    _real("orsay", "Musée d'Orsay", "museum", "https://www.musee-orsay.fr/en", ["musee-orsay.fr"], "FR"),
    _real("britishmuseum", "British Museum", "museum", "https://www.britishmuseum.org/visit", ["britishmuseum.org"], "GB",
          notes=("General admission is free; booking a timed slot is recommended.",)),
    _real("nationalgallery", "National Gallery", "gallery", "https://www.nationalgallery.org.uk/visiting",
          ["nationalgallery.org.uk"], "GB"),
    _real("prado", "Museo del Prado", "museum", "https://www.museodelprado.es/en", ["museodelprado.es"], "ES"),
    _real("rijksmuseum", "Rijksmuseum", "museum", "https://www.rijksmuseum.nl/en/tickets", ["rijksmuseum.nl"], "NL"),
    _real("vangogh", "Van Gogh Museum", "gallery", "https://www.vangoghmuseum.nl/en/tickets", ["vangoghmuseum.nl"], "NL"),
    _real("sagrada", "Sagrada Família", "attraction", "https://sagradafamilia.org/en/tickets", ["sagradafamilia.org"], "ES"),
    _real("acropolis", "Acropolis (Hellenic Heritage)", "attraction", "https://hhticket.gr/", ["hhticket.gr"], "GR"),
    _real("eiffel", "Eiffel Tower", "attraction", "https://www.toureiffel.paris/en", ["toureiffel.paris"], "FR"),
    _real("moma", "MoMA", "museum", "https://www.moma.org/visit", ["moma.org"], "US"),
    _real("met", "The Met", "museum", "https://www.metmuseum.org/plan-your-visit", ["metmuseum.org"], "US"),
)

SIMULATED_SITES: tuple[Site, ...] = (
    Site("demo_rail", "Ferrovia Demo (simulated rail)", "train", "/demo-sites/rail/", ("demo-sites/rail",), "EU",
         simulated=True, terms_note="Tandem's own simulated site — nothing real is booked or charged.",
         notes=("Full agentic purchase demo: search, select, approved passenger details, simulated payment.",)),
    Site("demo_coach", "CoachLine Demo (simulated bus)", "bus", "/demo-sites/coach/", ("demo-sites/coach",), "EU",
         simulated=True, terms_note="Tandem's own simulated site — nothing real is booked or charged."),
    Site("demo_air", "AeroDemo (simulated airline)", "flight", "/demo-sites/air/", ("demo-sites/air",), "EU",
         simulated=True, terms_note="Tandem's own simulated site — nothing real is booked or charged."),
    Site("demo_museum", "MuseoPass Demo (simulated museum & gallery tickets)", "museum", "/demo-sites/museum/",
         ("demo-sites/museum",), "EU", simulated=True,
         terms_note="Tandem's own simulated site — nothing real is booked or charged.",
         search_fields=("venue", "date", "time", "adults")),
)

ALL_SITES = {s.key: s for s in SIMULATED_SITES + REAL_SITES}


def assist_allow_list() -> set[str]:
    raw = current_app.config.get("BROWSER_ASSIST_SITES", "") or ""
    return {k.strip() for k in raw.split(",") if k.strip()}


def policy_for(site: Site) -> str:
    """simulated | assisted | link_only"""
    if site.simulated:
        return "simulated"
    if site.automation_forbidden:
        return "link_only"
    return "assisted" if site.key in assist_allow_list() else "link_only"


def agent_capabilities(site: Site) -> dict:
    policy = policy_for(site)
    from app.services.browser.engines import playwright_available

    return {
        "search": policy == "simulated" or (policy == "assisted" and playwright_available()),
        "select": policy == "simulated" or (policy == "assisted" and playwright_available()),
        "enter_traveller_details": policy == "simulated",  # real sites: hand-off before personal data
        "payment": "simulated_after_approval" if policy == "simulated" else "user_completes_on_site",
        "deep_link": bool(site.deep_link),
    }


def get_site(key: str) -> Site | None:
    return ALL_SITES.get(key)


def sites_for(user_is_demo: bool) -> list[Site]:
    """Demo workspaces see the simulated sites first; every account sees the real directory (link-outs)."""
    return list(SIMULATED_SITES) + list(REAL_SITES)


def handoff_url(site: Site, params: dict) -> str:
    """Verified deep link when available, otherwise the official homepage."""
    if site.deep_link and site.deep_link_checked and all(params.get(p) for p in site.deep_link_params):
        return site.deep_link.format(**{k: quote(str(v)) for k, v in params.items()})
    return site.homepage
