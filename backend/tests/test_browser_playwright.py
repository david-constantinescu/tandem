"""Playwright engine + AI navigator against a local fixture website (real headless Chromium, scripted model)."""
from __future__ import annotations

import functools
import http.server
import json
import threading
from pathlib import Path

import pytest

pytest.importorskip("playwright")

from app.extensions import db  # noqa: E402
from app.models import BrowserTask  # noqa: E402
from app.services.ai.base import AIProvider, AIResponse  # noqa: E402
from app.services.browser import sites as sites_mod  # noqa: E402
from app.services.browser.sites import Site  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures" / "site"


def _serve(disallow: bool):
    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            path = self.path.split("?")[0]
            if path == "/robots.txt":
                body = ("User-agent: *\nDisallow: /\n" if disallow else "User-agent: *\nAllow: /\n").encode()
                ctype = "text/plain"
            else:
                file = FIXTURES / (path.lstrip("/") or "index.html")
                if not file.is_file():
                    self.send_error(404)
                    return
                body = file.read_text().replace("PORT", str(self.server.server_port)).encode()
                ctype = "text/html"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Handler, directory=str(FIXTURES)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


@pytest.fixture
def site_server():
    servers = []

    def start(disallow=False):
        s = _serve(disallow)
        servers.append(s)
        return s

    yield start
    for s in servers:
        s.shutdown()


class Scripted(AIProvider):
    name = "gemini"

    def __init__(self, steps):
        self.steps = list(steps)

    def configured(self):
        return True

    def model_for(self, role):
        return "gemini-3.8-flash"

    def capabilities(self):
        return {}

    def generate(self, request, model):
        step = self.steps.pop(0) if self.steps else {"action": "handoff", "reason": "out of script"}
        return AIResponse(provider="gemini", model=model, text=json.dumps(step))


@pytest.fixture
def browser_env(app, monkeypatch, api):
    monkeypatch.setitem(app.config, "BROWSER_WORKER_ENABLED", True)
    monkeypatch.setitem(app.config, "BROWSER_ASSIST_SITES", "fixture")
    monkeypatch.setitem(app.config, "DEMO_ALLOW_EXTERNAL_AI", True)
    api.demo()

    def install(server, steps, homepage="index.html"):
        port = server.server_port
        site = Site("fixture", "Fixture Rail", "train", f"http://127.0.0.1:{port}/{homepage}", ("127.0.0.1",))
        monkeypatch.setitem(sites_mod.ALL_SITES, "fixture", site)
        from app.services.ai import router as router_mod

        monkeypatch.setattr(router_mod, "build_providers", lambda cfg: {"gemini": Scripted(steps)})
        return site

    return install


def _run(api, **params):
    r = api.post("/api/v1/browser/tasks", json={"site": "fixture", "origin": "Rome", "destination": "Florence",
                                                "date": "2026-11-15", **params})
    assert r.status_code == 201, r.get_json()
    return r.get_json()["data"]


def test_search_and_extract_then_stop(api, browser_env, site_server):
    server = site_server()
    browser_env(server, [
        {"action": "fill", "element_id": "e1", "value_key": "origin", "reason": "origin"},
        {"action": "fill", "element_id": "e2", "value_key": "destination", "reason": "destination"},
        {"action": "fill", "element_id": "e3", "value_key": "date_dmy", "reason": "date"},
        {"action": "fill", "element_id": "e3", "value_key": None, "reason": "model tries to invent a value"},
        {"action": "click", "element_id": "e4", "reason": "search"},
        {"action": "extract", "reason": "results visible", "offers": [
            {"title": "FR 9512", "depart": "08:10", "arrive": "10:05", "price": 39, "currency": "EUR"}]},
    ])
    t = _run(api)
    assert t["state"] == "completed", t
    assert t["engine"] == "playwright"
    assert t["result"]["offers"][0]["title"] == "FR 9512"
    actions = [s["action"] for s in t["log"]]
    assert actions[:4] == ["open", "fill", "fill", "fill"] and "skipped" in actions and "click" in actions
    assert any(s.get("screenshot") for s in t["log"])
    shot = next(s for s in t["log"] if s.get("screenshot"))
    img = api.get(f"/api/v1/browser/tasks/{t['id']}/steps/{shot['step']}/screenshot")
    assert img.status_code == 200 and img.mimetype == "image/jpeg"


def test_hands_off_before_personal_details(api, browser_env, site_server):
    server = site_server()
    browser_env(server, [{"action": "click", "element_id": "e1", "reason": "choose first train"}], homepage="results.html")
    t = _run(api)
    assert t["state"] == "requires_manual" and "personal or payment" in t["stop_reason"]


def test_stops_on_captcha(api, browser_env, site_server):
    server = site_server()
    browser_env(server, [], homepage="captcha.html")
    t = _run(api)
    assert t["state"] == "waiting_for_user" and "never solves CAPTCHAs" in t["stop_reason"]


def test_blocks_off_site_navigation(api, browser_env, site_server):
    server = site_server()
    browser_env(server, [{"action": "click", "element_id": "e3", "reason": "partner offers"}], homepage="results.html")
    t = _run(api)
    assert t["state"] == "blocked" and "outside" in t["stop_reason"]


def test_respects_robots_txt(api, browser_env, site_server):
    server = site_server(disallow=True)
    browser_env(server, [])
    t = _run(api)
    assert t["state"] == "blocked" and "robots.txt" in t["stop_reason"]


def test_never_fills_card_fields(app, site_server):
    from app.services.browser.engines import PlaywrightEngine
    from app.services.browser.policy import PolicyViolation

    server = site_server()
    site = Site("fixture", "Fixture Rail", "train", f"http://127.0.0.1:{server.server_port}/card.html", ("127.0.0.1",))
    eng = PlaywrightEngine(site)
    try:
        snap = eng.goto(site.homepage)
        card = snap.find(name="cardnumber")
        assert card["sensitive"]
        with pytest.raises(PolicyViolation):
            eng.fill(card["id"], "4111111111111111")
    finally:
        eng.close()
    assert db.session.execute(db.select(BrowserTask)).first() is None
