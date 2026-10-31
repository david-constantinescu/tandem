"""Server text is Romanian by default and English on request; every template must have a Romanian version."""
from __future__ import annotations

import pathlib
import re
import string

from app.i18n import T, When, long_date, tr
from app.locale_ro import RO

APP = pathlib.Path(__file__).resolve().parents[1] / "app"
LITERAL = r'"((?:[^"\\]|\\.)*)"'


def _templates() -> set[str]:
    """English templates passed to T()/tr(), including implicit concatenation and if/else variants."""
    found: set[str] = set()
    for path in APP.rglob("*.py"):
        src = path.read_text()
        for m in re.finditer(r"\b(?:T|tr)\(\s*((?:" + LITERAL + r"\s*)+)", src):
            found.add("".join(re.findall(LITERAL, m.group(1))))
        for m in re.finditer(r"\b(?:T|tr)\(\s*" + LITERAL + r"\s+if\s+[^,]*?\s+else\s+" + LITERAL, src):
            found.add(m.group(2))
        for m in re.finditer(r"raise (?:NotFound|Unauthorized|Forbidden|Conflict|ValidationFailed)\(\s*" + LITERAL, src):
            if "{" not in m.group(1):
                found.add(m.group(1))
    return found


def _fields(template: str) -> set[str]:
    return {f for _, f, _, _ in string.Formatter().parse(template) if f}


def test_every_template_has_romanian_with_the_same_placeholders():
    missing = sorted(t for t in _templates() if t not in RO)
    assert not missing, f"add Romanian for: {missing[:10]}"
    wrong = [k for k, v in RO.items() if _fields(k) != _fields(v)]
    assert not wrong, f"placeholders differ: {wrong}"
    cedilla = [k for k, v in RO.items() if re.search("[şţŞŢ]", v)]
    assert not cedilla, f"use comma-below ș/ț: {cedilla}"


def test_rendering_follows_the_language(app):
    with app.test_request_context(headers={"X-Tandem-Locale": "en"}):
        assert tr("Free afternoon") == "Free afternoon"
        assert T("{a} overlaps {b}", a="Tour", b="Dinner").render() == "Tour overlaps Dinner"
    with app.test_request_context(headers={"X-Tandem-Locale": "ro"}):
        assert tr("Free afternoon") == "După-amiază liberă"
        assert T("{a} overlaps {b}", a="Tur", b="Cină").render() == "Tur se suprapune cu Cină"
    with app.test_request_context():  # no header and no user: Romanian
        assert tr("Free afternoon") == "După-amiază liberă"
    from datetime import date, datetime
    assert When(datetime(2026, 11, 14, 17, 30)).render("ro") == "sâm. 14 nov. 17:30"
    assert When(datetime(2026, 11, 14, 17, 30)).render("en") == "Sat 14 Nov 17:30"
    assert long_date(date(2026, 11, 14), "ro") == "sâmbătă, 14 noiembrie"


def test_errors_and_conflicts_come_back_in_the_requested_language(api, app):
    anonymous = app.test_client()
    r = anonymous.post("/api/v1/auth/login", json={"email": "nobody@example.com", "password": "x"},
                       headers={"X-Tandem-Locale": "ro"})
    assert r.get_json()["error"]["message"] == "Email sau parolă incorecte"
    r = anonymous.post("/api/v1/auth/login", json={"email": "nobody@example.com", "password": "x"},
                       headers={"X-Tandem-Locale": "en"})
    assert r.get_json()["error"]["message"] == "Incorrect email or password"


def test_demo_is_seeded_in_the_visitors_language(app):
    for locale, trip_name, overlap in (("ro", "Weekend prelungit la Roma", "se suprapune cu"),
                                       ("en", "Rome long weekend", "overlaps")):
        client = app.test_client()
        r = client.post("/api/v1/auth/demo", json={"locale": locale}, headers={"X-Tandem-Locale": locale})
        assert r.status_code == 201, r.get_json()
        assert r.get_json()["data"]["user"]["locale"] == locale
        csrf = r.get_json()["data"]["csrf_token"]
        trips = client.get("/api/v1/trips", headers={"X-Tandem-Locale": locale}).get_json()["data"]
        assert trips[0]["name"] == trip_name
        conflicts = client.get(f"/api/v1/trips/{trips[0]['id']}/conflicts", headers={"X-Tandem-Locale": locale}).get_json()["data"]
        assert any(overlap in c["title"] for c in conflicts)
        # Place names are data: translating the trip's city must not invent a missing journey.
        assert not any(c["type"] == "missing_transport" for c in conflicts)
        notes = client.get("/api/v1/notifications", headers={"X-Tandem-Locale": locale}).get_json()["data"]
        assert notes and all(n["title"] for n in notes)
        # The offline assistant answers a question in the same language.
        conv = client.post("/api/v1/assistant/conversations", json={"trip_id": trips[0]["id"]},
                           headers={"X-CSRF-Token": csrf, "X-Tandem-Locale": locale}).get_json()["data"]
        question = "Ce nu e confirmat încă?" if locale == "ro" else "What's still unconfirmed?"
        reply = client.post(f"/api/v1/assistant/conversations/{conv['id']}/messages", json={"content": question},
                            headers={"X-CSRF-Token": csrf, "X-Tandem-Locale": locale}).get_json()["data"]
        text = reply["messages"][-1]["content"]
        assert ("Asistent offline" in text) if locale == "ro" else ("Offline assistant" in text)
