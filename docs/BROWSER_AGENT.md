# Browser agent

Tandem's browser agent uses booking websites on the user's behalf: trains, buses, flights, museums,
galleries and attractions. UI: **Websites** page (and the assistant's `start_website_task` tool).
Code: `backend/app/services/browser/` (sites, policy, engines, agent), `backend/app/api/browser.py`,
simulated sites in `backend/app/api/demo_sites.py`.

## What it does on each kind of site

| Site kind | Policy | What the agent does |
|---|---|---|
| **Tandem's simulated sites** (Ferrovia Demo rail, CoachLine Demo bus, AeroDemo airline, MuseoPass Demo museums & galleries) | `simulated` | Full purchase: open → fill the search form → read and compare results → pick an option that fits the itinerary (earliest after your preferred time, otherwise cheapest) → **pause for approval** → enter the approved names → simulated payment → read the confirmation page back → verify it against the approval → import a verified reservation into the trip. Nothing real is booked or charged. |
| **Real sites, default** (42 sites: Trenitalia, Italo, SNCF Connect, Deutsche Bahn, Eurostar, Renfe, ÖBB, SBB, CFR Călători, Trainline, Omio, FlixBus, BlaBlaCar Bus, National Express, Megabus, ALSA, RegioJet, Ryanair, Wizz Air, easyJet, TAROM, Lufthansa, British Airways, Air France, KLM, ITA Airways, American Airlines, Vatican Museums, Colosseum, Uffizi, Louvre, Musée d'Orsay, British Museum, National Gallery, Prado, Rijksmuseum, Van Gogh Museum, Sagrada Família, Acropolis, Eiffel Tower, MoMA, The Met) | `link_only` | No automation. The run hands off immediately with the official URL, and you book there and forward the confirmation to the Inbox. Terms of service have not been reviewed for automated access; **Ryanair's terms prohibit it**, so it can never be enabled. |
| **Real sites the operator allow-lists** (`BROWSER_ASSIST_SITES=trainline,flixbus`, after reviewing each site's terms) | `assisted` | With a browser worker (Playwright) and an AI provider: the navigator model searches and compares on that site only, then **hands off before any personal-data or payment page**. Real-site carts don't carry over to your own browser; the hand-off link opens the site. |

## Guards (enforced in code, not prompts)

- **Domain allow-list:** every navigation, including redirects, must stay on the site's domains.
  Country redirects are matched safely (`klm.ro` and `airfrance.co.uk` match, `airfrance.evil.com` does not).
- **robots.txt** is honoured for real sites (user agent `TandemBrowserAgent`); a disallow blocks the run.
- **Constrained actions only:** observe (snapshot of visible controls with ids), fill, select, click.
  The model names an element id and a task-parameter key; it never supplies JavaScript, selectors,
  URLs or free-text values. Select options must exist on the page.
- **Never filled:** password, card, CVV, expiry, IBAN, passport, national ID and one-time-code fields
  (detected by input type, `autocomplete`, name, label and placeholder). Personal-detail fields are
  only filled on simulated sites after approval.
- **Stop conditions:** reCAPTCHA, hCaptcha, Cloudflare Turnstile, DataDome, PerimeterX, Akamai and
  generic "verify you are human" pages → `waiting_for_user` and stop. Login walls → stop. Tandem never
  solves or bypasses challenges, uses no stealth plugins and does not spoof its user agent.
- **Approval bound to the exact payload** (site, offer, date, times, travellers, total). Before paying,
  the agent re-reads the amount on the site; a different amount stops the run ("Nothing was paid").
  After paying, the confirmation must match date, departure, total and number of travellers.
- **Screenshots** (Playwright) mask sensitive fields before they're stored; they're served only to the owner.
- Step limit 15; every step is logged (action, reason, URL, screenshot or page text) and audited.

## Engines

- **HttpEngine:** form-level browser for Tandem's own simulated sites, executed in-process through the
  Flask app. Works everywhere, including Vercel and the test suite.
- **PlaywrightEngine:** headless Chromium (or `BROWSER_CDP_URL`) for real sites, run by a browser worker:
  `flask worker --only browser_task` (Docker: `Dockerfile.browser`, Compose service `browser-worker`).
  Not available on Vercel; the Websites page says so and real sites stay link-only there.

## States

not_started · searching · navigating · awaiting_approval · submitting · verifying · completed ·
requires_manual (hand-off) · waiting_for_user (challenge) · blocked (policy) · failed · cancelled.

## Configuration

```
BROWSER_WORKER_ENABLED=false   # true on the web service when a browser worker runs (never on Vercel)
BROWSER_ASSIST_SITES=          # real site keys allowed for assisted search after terms review
BROWSER_CDP_URL=               # optional remote Chromium endpoint
```

## Tests

`tests/test_browser_agent.py` (registry, policy, simulated purchases incl. price-change stop, cancel,
offline assistant booking) and `tests/test_browser_playwright.py` (real headless Chromium against a
local fixture site with a scripted model: search and extract, hand-off before personal details,
CAPTCHA stop, off-site redirect block, robots.txt disallow, card fields never filled).

## Link checks (2026-10-30)

All 42 official URLs were checked. 23 answer scripted requests directly; 15 return 403 to non-browser
clients (bot protection — consistent with keeping them link-only); Trenitalia, the Vatican ticket office,
Air France and KLM only answer real browsers and were confirmed in one. Deep-link templates are not
listed for any real site yet: none has been verified to land on a populated search, so hand-offs open
the official page.
