"""Verificare completa pe productie, endpoint cu endpoint, intr-un spatiu demo (nu face conturi reale).

    python scripts/prod_full_check.py [https://tandem.softhoarders.me]

Nu foloseste AI decat unde e inevitabil (explicatia unui conflict). Testele cu AI sunt in prod_ai_check.py.
"""
from __future__ import annotations

import http.cookiejar
import json
import sys
import time
import urllib.error
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "https://tandem.softhoarders.me").rstrip("/")
API = BASE + "/api/v1"
jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
csrf = ""
results: list[tuple[str, bool, str]] = []


def call(method, path, body=None, raw=False, timeout=75, headers=None):
    h = {"X-Tandem-Locale": "ro", "X-CSRF-Token": csrf, **(headers or {})}
    data = json.dumps(body).encode() if body is not None else None
    if data is not None:
        h["Content-Type"] = "application/json"
    url = path if path.startswith("http") else API + path
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        r = opener.open(req, timeout=timeout)
        content = r.read()
        return r.status, (content if raw else json.loads(content or b"{}")), dict(r.headers)
    except urllib.error.HTTPError as e:
        content = e.read() or b""
        try:
            return e.code, (content if raw else json.loads(content or b"{}")), dict(e.headers)
        except ValueError:
            return e.code, {"error": content[:200].decode("utf-8", "replace")}, dict(e.headers)


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("PASS " if ok else "FAIL ") + name + (f"  - {str(detail)[:170]}" if detail else ""))
    sys.stdout.flush()


def step(name, fn):
    try:
        fn()
    except Exception as exc:  # noqa: BLE001 - a broken step is a failure, not the end of the run
        check(name, False, f"{type(exc).__name__}: {exc}")


def main() -> int:
    global csrf
    s, d, _ = call("GET", "/health")
    check("health", s == 200 and d["data"]["database"], d.get("data"))
    s, d, _ = call("GET", "/openapi.json")
    check("openapi document", s == 200 and len(d.get("paths", {})) > 80, f"{len(d.get('paths', {}))} paths")
    s, page, hdr = call("GET", BASE + "/", raw=True)
    check("site loads with security headers", s == 200 and b"<div id=\"root\">" in page
          and "default-src 'self'" in hdr.get("Content-Security-Policy", "") and hdr.get("X-Frame-Options") == "DENY",
          hdr.get("Content-Security-Policy", "")[:80])
    s, d, _ = call("GET", "/trips")
    check("signed out is refused", s == 401)

    s, d, _ = call("POST", "/auth/demo", {})
    csrf = d["data"]["csrf_token"]
    me = d["data"]["user"]
    check("demo workspace", s == 201 and me["home_city"] == "Craiova", me["display_name"])
    s, d, _ = call("GET", "/auth/me")
    check("me", s == 200 and d["data"]["user"]["id"] == me["id"])
    s, d, _ = call("POST", "/trips", {"name": "x"}, headers={"X-CSRF-Token": "wrong"})
    check("write without a valid CSRF token is refused", s == 403, d.get("error", {}).get("code"))

    s, d, _ = call("GET", "/trips")
    trip = d["data"][0]
    tid = trip["id"]
    check("trips list", s == 200 and trip["start_date"], f"{trip['name']} {trip['start_date']}..{trip['end_date']}")
    ctx = {}

    def trips():
        s, d, _ = call("GET", f"/trips/{tid}")
        check("trip detail", s == 200 and len(d["data"]["travellers"]) >= 1, [t["full_name"] for t in d["data"]["travellers"]])
        s, d, _ = call("POST", "/trips", {"name": "Test Cluj", "primary_destination": "Cluj-Napoca", "start_date": "2026-12-05", "end_date": "2026-12-07"})
        ctx["trip2"] = d["data"]["id"]
        check("create trip", s == 201 and d["data"]["primary_destination"] == "Cluj-Napoca")
        s, d, _ = call("PATCH", f"/trips/{ctx['trip2']}", {"name": "Test Cluj (renamed)", "notes": "note de test"})
        check("edit trip", s == 200 and d["data"]["name"].endswith("(renamed)"))
        s, d, _ = call("POST", f"/trips/{ctx['trip2']}/destinations", {"name": "Sibiu"})
        check("add destination", s == 201, [x["name"] for x in (d.get("data") or {}).get("destinations", [])] if isinstance(d.get("data"), dict) else d)
        s, d, _ = call("POST", f"/trips/{ctx['trip2']}/travellers", {"full_name": "Maria Test"})
        check("add traveller", s == 201)
        for sub in ("map", "documents", "conflicts", "itinerary", "reservations", "context"):
            s, d, _ = call("GET", f"/trips/{tid}/{sub}")
            check(f"trip {sub}", s == 200, f"{len(d['data']) if isinstance(d.get('data'), list) else list((d.get('data') or {}).keys())[:4]}")
        s, d, _ = call("GET", f"/trips/{tid}/conflicts")
        ctx["conflicts"] = d["data"]
        check("demo clash is detected", any("Trastevere" in c["title"] for c in d["data"]), [c["title"] for c in d["data"]][:2])
    step("trips", trips)

    def itinerary():
        sat = (time.strftime("%Y") + trip["start_date"][4:])  # same year as the trip
        day = trip["start_date"][:8] + f"{int(trip['start_date'][8:]) + 1:02d}"
        s, d, _ = call("POST", "/itinerary/events", {"trip_id": tid, "title": "Pantheon", "type": "museum",
                                                    "start_local": f"{day}T15:00", "end_local": f"{day}T16:00", "location_name": "Pantheon"})
        ev = d.get("data", {})
        check("add event", s == 201 and ev.get("start_local", "").startswith(f"{day}T15:00"), ev.get("start_local"))
        s, d, _ = call("PATCH", f"/itinerary/events/{ev['id']}", {"start_local": f"{day}T16:30", "end_local": f"{day}T17:30"})
        check("move event", s == 200 and d["data"]["start_local"].startswith(f"{day}T16:30"), d["data"]["start_local"])
        s, d, _ = call("PATCH", f"/itinerary/events/{ev['id']}", {"status": "completed"})
        check("mark event done", s == 200 and d["data"]["status"] == "completed")
        s, d, _ = call("DELETE", f"/itinerary/events/{ev['id']}")
        check("delete event", s == 200)
        _ = sat
    step("itinerary", itinerary)

    def reservations():
        s, d, _ = call("GET", "/reservations")
        check("all reservations", s == 200 and len(d["data"]) >= 6, len(d["data"]))
        res = d["data"][0]
        s, d, _ = call("GET", f"/reservations/{res['id']}")
        check("reservation detail", s == 200 and d["data"]["booking_reference"])
        s, d, _ = call("GET", f"/reservations/{res['id']}/changes")
        check("reservation history", s == 200)
        s, d, _ = call("POST", "/reservations", {"type": "restaurant", "title": "Cina la Roscioli", "trip_id": tid,
                                                 "start_local": trip["start_date"] + "T20:00", "start_tz": "Europe/Rome",
                                                 "location_name": "Roscioli", "city": "Rome", "status": "confirmed",
                                                 "booking_reference": "TEST-1"})
        r2 = d.get("data", {})
        check("add reservation by hand", s == 201 and r2.get("booking_reference") == "TEST-1", r2.get("start_local"))
        s, d, _ = call("PATCH", f"/reservations/{r2['id']}", {"title": "Cina la Roscioli (2 pers)"})
        check("edit reservation", s == 200 and "(2 pers)" in d["data"]["title"])
        s, d, _ = call("POST", f"/reservations/{r2['id']}/move", {"trip_id": ctx["trip2"]})
        check("move reservation to another trip", s == 200 and d["data"]["trip_id"] == ctx["trip2"], d.get("data", {}).get("trip_id"))
        s, d, _ = call("DELETE", f"/reservations/{r2['id']}")
        check("delete reservation", s == 200)
    step("reservations", reservations)

    def inbox():
        s, d, _ = call("GET", "/demo/samples")
        samples = d["data"]
        check("sample documents", s == 200 and len(samples) == 3, [x["key"] for x in samples])
        s, raw, hdr = call("GET", f"/demo/samples/{samples[0]['key']}", raw=True)
        check("download a sample", s == 200 and raw[:4] == b"%PDF", hdr.get("Content-Type"))
        docs = []
        for sm in samples:
            s, d, _ = call("POST", f"/demo/samples/{sm['key']}/upload", {}, timeout=90)
            ok = s in (200, 201)
            if ok:
                docs.append(d["data"])
            check(f"read sample {sm['key']}", ok and d["data"]["status"] in ("awaiting_review", "processed"),
                  f"{d.get('data', {}).get('status')} via {d.get('data', {}).get('extraction_method', {}).get('path')}")
        s, d, _ = call("POST", "/inbox/paste", {"title": "Rezervare Armando", "text": "Your table is confirmed\nRestaurant: Armando al Pantheon\n"
                                                "Date: 13 November 2026\nTime: 20:30\nReservation for 2 people\nReservation number: AAP-2290\n"
                                                "Address: Salita dei Crescenzi 31, 00186 Rome"}, timeout=90)
        ctx["pasted"] = d.get("data", {})
        check("paste an email", s in (200, 201) and ctx["pasted"].get("status") in ("awaiting_review", "processed"), ctx["pasted"].get("status"))
        s, d, _ = call("POST", "/inbox/url", {"url": "http://169.254.169.254/latest/meta-data/"})
        check("link to a private address is refused (SSRF)", s in (400, 422), d.get("error", {}).get("code"))
        s, d, _ = call("POST", "/inbox/url", {"url": "https://example.com/"}, timeout=60)
        check("read a public link", s in (200, 201), d.get("data", {}).get("status") or d.get("error"))
        s, d, _ = call("GET", "/inbox")
        items = d["data"]["data"] if isinstance(d["data"], dict) else d["data"]
        check("inbox list", s == 200 and len(items) >= 4, len(items))
        review = next((x for x in docs + [ctx["pasted"]] if x.get("status") == "awaiting_review"), None)
        if review:
            s, d, _ = call("GET", f"/inbox/{review['id']}")
            recs = d["data"]["records"]
            check("inbox item with records", s == 200 and recs, [r["data"].get("title") for r in recs])
            s, d, _ = call("POST", f"/inbox/{review['id']}/review", {"decisions": [{"record_id": r["id"], "decision": "accept"} for r in recs]}, timeout=90)
            check("accept what was read", s == 200 and all(x.get("trip_id") for x in d["data"]["results"]),
                  [(x.get("status"), x.get("trip_id", "")[:8]) for x in d["data"]["results"]])
        s, d, _ = call("GET", "/documents")
        alld = d["data"]
        check("documents list", s == 200 and len(alld) >= 3, len(alld))
        doc = alld[0]
        s, d, _ = call("GET", f"/documents/{doc['id']}")
        check("document detail", s == 200)
        s, raw, hdr = call("GET", f"/documents/{doc['id']}/download", raw=True)
        check("document download is private and not inline-executable", s == 200 and "attachment" in hdr.get("Content-Disposition", ""),
              hdr.get("Content-Disposition"))
        s, raw, hdr = call("GET", f"/documents/{doc['id']}/preview", raw=True)
        check("document preview", s in (200, 404), hdr.get("Content-Type"))
        other = next((x for x in alld if x["id"] != doc["id"]), None)
        if other:
            s, d, _ = call("POST", f"/inbox/{other['id']}/ignore", {})
            check("ignore a document", s == 200, d.get("data", {}).get("status") if isinstance(d.get("data"), dict) else d)
            s, d, _ = call("POST", f"/inbox/{other['id']}/retry", {}, timeout=90)
            check("re-read a document", s in (200, 201, 409), s)
            s, d, _ = call("DELETE", f"/inbox/{other['id']}")
            check("delete a document", s == 200)
    step("inbox", inbox)

    def activities():
        s, d, _ = call("GET", "/activities/providers")
        check("activity providers", s == 200 and any(p["key"] == "simulator" for p in d["data"]), [p["key"] for p in d["data"]])
        day = trip["start_date"][:8] + f"{int(trip['start_date'][8:]) + 3:02d}"
        s, d, _ = call("POST", "/activities/search", {"trip_id": tid, "categories": ["museums"], "date_from": day, "date_to": day}, timeout=60)
        res = d.get("data", {}).get("results", [])
        check("activity search", s == 200 and res, f"{len(res)} results, weather={bool(d['data'].get('weather'))}")
        sim = next((r for r in res if r["provider"] == "simulator"), None)
        if not sim:
            return
        s, d, _ = call("GET", f"/activities/simulator/{sim['provider_item_id']}")
        check("activity detail", s == 200 and d["data"]["title"] == sim["title"])
        s, d, _ = call("POST", f"/activities/simulator/{sim['provider_item_id']}/availability", {"date": day, "participants": 2})
        slots = d.get("data", {}).get("slots") or d.get("data", {}).get("available_slots") or []
        check("live availability", s == 200, f"{len(slots)} slots")
        s, d, _ = call("POST", "/activities/saved", {"provider": "simulator", "provider_item_id": sim["provider_item_id"], "trip_id": tid, "data": sim})
        saved_id = d.get("data", {}).get("id")
        check("save an activity", s == 201 and saved_id)
        s, d, _ = call("GET", "/activities/saved")
        check("saved list", s == 200 and any(x["id"] == saved_id for x in d["data"]))
        s, d, _ = call("DELETE", f"/activities/saved/{saved_id}")
        check("remove saved", s == 200)
        slot = slots[0] if slots else None
        s, d, _ = call("POST", "/activities/proposals", {"provider": "simulator", "provider_item_id": sim["provider_item_id"], "date": day,
                                                        "time": (slot or {}).get("time"), "participants": 2, "trip_id": tid})
        action = d.get("data", {})
        check("prepare a booking (needs approval)", s == 201 and action.get("status") == "awaiting_approval", action.get("title"))
        if action.get("id"):
            s, d, _ = call("POST", f"/approvals/{action['id']}/approve", {"payload_hash": "0" * 64})
            check("approval with the wrong payload hash is refused", s in (400, 409), d.get("error", {}).get("code"))
            s, d, _ = call("POST", f"/approvals/{action['id']}/approve", {"payload_hash": action["payload_hash"]}, timeout=60)
            check("approve the booking", s == 200 and d["data"]["status"] == "completed", d["data"].get("result", {}).get("provider_booking_id"))
    step("activities", activities)

    def approvals_and_browser():
        s, d, _ = call("GET", "/browser/sites")
        check("booking sites", s == 200 and any(x["key"] == "wizzair" for x in d["data"]), len(d["data"]))
        day = trip["start_date"]
        s, d, _ = call("POST", "/browser/tasks", {"site": "wizzair", "origin": "Craiova", "destination": "Roma", "date": day, "adults": 2, "trip_id": tid})
        check("Wizz Air hands off a prefilled link", s == 201 and "/CRA/FCO/" in (d["data"].get("handoff_url") or ""), d["data"].get("handoff_url"))
        s, d, _ = call("POST", "/browser/tasks", {"site": "demo_rail", "origin": "Roma", "destination": "Firenze", "date": day, "adults": 2, "trip_id": tid}, timeout=60)
        task = d.get("data", {})
        check("agent searches the practice rail site", s == 201 and task.get("state") == "awaiting_approval", task.get("result", {}).get("selected"))
        s, d, _ = call("GET", f"/browser/tasks/{task['id']}")
        steps = d["data"]["log"]
        check("agent step log", s == 200 and [x["action"] for x in steps][:3] == ["open", "search", "select"], [x["action"] for x in steps])
        shot = next((x for x in steps if x.get("screenshot")), None)
        if shot:
            s, raw, hdr = call("GET", f"/browser/tasks/{task['id']}/steps/{shot['step']}/screenshot", raw=True)
            check("step screenshot", s == 200 and hdr.get("Content-Type", "").startswith("image"), hdr.get("Content-Type"))
        s, d, _ = call("GET", "/approvals?status=awaiting_approval")
        pending = d["data"]
        check("approvals list", s == 200 and any(a["id"] == task["action_id"] for a in pending), len(pending))
        s, d, _ = call("POST", f"/approvals/{task['action_id']}/reject", {"note": "test"})
        check("decline the purchase", s == 200 and d["data"]["status"] in ("rejected", "declined", "cancelled"), d["data"]["status"])
        s, d, _ = call("POST", "/browser/tasks", {"site": "demo_air", "origin": "Craiova", "destination": "Roma", "date": day, "adults": 2, "trip_id": tid}, timeout=60)
        t2 = d["data"]
        s, a, _ = call("GET", f"/approvals/{t2['action_id']}")
        s, first, _ = call("POST", f"/approvals/{t2['action_id']}/approve", {"payload_hash": a["data"]["payload_hash"]}, timeout=60)
        pay_id = first["data"]["result"]["payment_action_id"]
        s, pay, _ = call("GET", f"/approvals/{pay_id}")
        check("first approval stops on the payment page", pay["data"]["action_type"] == "browser_payment" and pay["data"]["status"] == "awaiting_approval", pay["data"]["title"])
        s, done, _ = call("POST", f"/approvals/{pay_id}/approve", {"payload_hash": pay["data"]["payload_hash"]}, timeout=60)
        check("second approval pays (simulated) and books", done["data"]["status"] == "completed", done["data"].get("result", {}).get("provider_booking_id"))
        s, d, _ = call("GET", "/browser/tasks")
        check("task list", s == 200 and len(d["data"]) >= 3, len(d["data"]))
        s, d, _ = call("POST", "/browser/tasks", {"site": "demo_coach", "origin": "Roma", "destination": "Napoli", "date": day, "adults": 1}, timeout=60)
        if d.get("data", {}).get("id"):
            s, d2, _ = call("POST", f"/browser/tasks/{d['data']['id']}/cancel", {})
            check("cancel an agent task", s == 200 and d2["data"]["state"] == "cancelled", d2["data"].get("state"))
    step("browser agent", approvals_and_browser)

    def calendar():
        s, raw, hdr = call("GET", f"/calendar/trips/{tid}.ics", raw=True)
        check("trip calendar file", s == 200 and raw.startswith(b"BEGIN:VCALENDAR") and raw.count(b"BEGIN:VEVENT") >= 6, raw.count(b"BEGIN:VEVENT"))
        s, d, _ = call("POST", "/calendar/subscription", {})
        feed = d.get("data", {}).get("url") or d.get("data", {}).get("feed_url")
        check("calendar subscription", s in (200, 201) and feed, feed and feed[:60])
        if feed:
            s, raw, _ = call("GET", feed if feed.startswith("http") else BASE + feed, raw=True)
            check("subscription feed", s == 200 and raw.startswith(b"BEGIN:VCALENDAR"))
        s, d, _ = call("GET", "/calendar/subscription")
        check("subscription status", s == 200)
        s, d, _ = call("DELETE", "/calendar/subscription")
        check("revoke subscription", s == 200)
        if feed:
            s, raw, _ = call("GET", feed if feed.startswith("http") else BASE + feed, raw=True)
            check("revoked feed stops working", s in (401, 403, 404))
    step("calendar", calendar)

    def settings_and_more():
        for path in ("/settings", "/settings/ai", "/settings/providers", "/settings/usage", "/settings/sessions", "/integrations", "/notifications"):
            s, d, _ = call("GET", path)
            check(f"GET {path}", s == 200)
        s, d, _ = call("PATCH", "/settings/profile", {"home_city": "Craiova", "home_airport": "CRA", "locale": "ro"})
        check("edit profile", s == 200)
        s, d, _ = call("PATCH", "/settings/preferences", {"interests": ["history", "food", "art"], "pace": "relaxed", "budget": "moderate"})
        check("edit preferences", s == 200)
        s, d, _ = call("PUT", "/settings/ai", {"mode": "full", "acknowledge_privacy": True})
        check("AI settings", s == 200)
        s, raw, hdr = call("GET", "/settings/export", raw=True)
        check("export my data", s == 200 and len(raw) > 1000, f"{len(raw)} bytes {hdr.get('Content-Type')}")
        s, d, _ = call("GET", "/notifications")
        notes = d["data"]
        if notes:
            s, _, _ = call("POST", f"/notifications/{notes[0]['id']}/read", {})
            check("read a notification", s == 200)
        s, d, _ = call("POST", "/notifications/read-all", {})
        check("read all notifications", s == 200)
        s, d, _ = call("GET", "/journeys?origin=Craiova&destination=Roma&date=" + trip["start_date"])
        check("journeys", s == 200 and d["data"]["links"][0]["name"] == "Google Maps", [x["name"] for x in d["data"]["links"]][:5])
        if ctx.get("conflicts"):
            s, d, _ = call("POST", f"/trips/{tid}/conflicts/explain", {}, timeout=60)
            check("explain a clash (AI)", s == 200, str(d.get("data"))[:120])
        s, d, _ = call("DELETE", f"/trips/{ctx['trip2']}")
        check("delete trip", s == 200)
    step("settings", settings_and_more)

    def assistant_basics():
        s, d, _ = call("POST", "/assistant/check-in", {})
        check("check-in", s == 200 and d["data"]["updates_conversation_id"], d["data"])
        s, d, _ = call("GET", "/assistant/conversations")
        upd = next((c for c in d["data"] if c["kind"] == "updates"), None)
        check("Tandem's own updates conversation", upd is not None)
        s, d, _ = call("GET", f"/assistant/conversations/{upd['id']}")
        proactive = [m for m in d["data"]["messages"] if m["model"] == "proactive"]
        check("proactive message with answers", proactive and any(r["type"] == "choices" for r in proactive[0]["references"]), proactive[0]["content"][:100] if proactive else "")
        s, d, _ = call("POST", "/assistant/conversations", {"trip_id": tid})
        cid = d["data"]["id"]
        s, doc, _ = call("POST", "/inbox/paste", {"text": "Booking confirmed. Hotel Santa Maria, Rome. Check-in 12 November 2026 from 15:00. Confirmation HSM-58213."}, timeout=90)
        s, d, _ = call("POST", f"/assistant/conversations/{cid}/attachments", {"document_ids": [doc["data"]["id"]]}, timeout=60)
        msgs = d.get("data", {}).get("messages", [])
        check("upload lands in the chat with a reply", s == 201 and msgs[-2]["role"] == "user" and msgs[-1]["role"] == "assistant", msgs[-1]["content"][:120] if msgs else d)
        s, d, _ = call("DELETE", f"/assistant/conversations/{cid}")
        check("delete a conversation", s == 200)
    step("assistant basics", assistant_basics)

    s, d, _ = call("POST", "/auth/logout", {})
    check("sign out", s == 200)
    s, d, _ = call("GET", "/trips")
    check("signed out afterwards", s == 401)

    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed")
    for name, _, detail in failed:
        print("  FAILED:", name, "-", str(detail)[:200])
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
