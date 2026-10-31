"""End to end over HTTP against a running Tandem (production by default): a demo workspace, every assistant ability
with the real AI, the live weather/news/journey sources, and the inbox pipeline. Spends free-tier AI quota, so it is
not part of the test suite.

    python scripts/prod_e2e.py [https://tandem.softhoarders.me]
"""
from __future__ import annotations

import http.cookiejar
import json
import sys
import time
import urllib.error
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "https://tandem.softhoarders.me").rstrip("/") + "/api/v1"
jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
csrf = ""
results: list[bool] = []


def call(method: str, path: str, body=None, timeout: int = 75):
    headers = {"X-Tandem-Locale": "ro", "X-CSRF-Token": csrf}
    data = json.dumps(body).encode() if body is not None else None
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        r = opener.open(req, timeout=timeout)
        return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        raw = e.read() or b""
        try:
            return e.code, json.loads(raw or b"{}")
        except ValueError:
            return e.code, {"error": raw[:200].decode("utf-8", "replace")}


def check(name: str, ok, detail: str = "") -> None:
    results.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name + (f"  - {detail}" if detail else ""))
    sys.stdout.flush()


def short(reply) -> str:
    return reply["content"][:150].replace("\n", " ") if reply else ""


def main() -> int:
    global csrf
    s, d = call("POST", "/auth/demo", {})
    csrf = (d.get("data") or {}).get("csrf_token") or (d.get("meta") or {}).get("csrf_token", "")
    user = (d.get("data") or {}).get("user") or {}
    check("demo workspace from Craiova", s == 201 and user.get("home_city") == "Craiova", f"{user.get('display_name')}, {user.get('home_city')}")
    s, d = call("GET", "/trips")
    trip = d["data"][0]
    tid = trip["id"]
    s, d = call("GET", f"/trips/{tid}/reservations")
    titles = {r["title"] for r in d["data"]}
    check("real names, sample bookings", any("Hotel Santa Maria" in t for t in titles) and any("CRA" in t for t in titles), "; ".join(sorted(titles))[:110])
    s, d = call("GET", f"/trips/{tid}/context")
    w, n = d["data"]["weather"], d["data"]["news"]
    check("live weather (Open-Meteo)", w["available"] and len(w["days"]) >= 4, f"{len(w['days'])} days")
    check("live local news", n["available"], f"{len(n['items'])} items via {n.get('source')}")
    s, d = call("GET", "/journeys?origin=Craiova&destination=Roma&date=2026-11-12")
    check("journey links", s == 200 and len(d["data"]["links"]) >= 5, ", ".join(x["name"] for x in d["data"]["links"][:6]))

    s, d = call("POST", "/assistant/conversations", {"trip_id": tid})
    cid = d["data"]["id"]

    def ask(text: str):
        t0 = time.time()
        s, d = call("POST", f"/assistant/conversations/{cid}/messages", {"content": text})
        if s not in (200, 201):
            print(f"  (HTTP {s}: {str(d)[:300]})")
            return None, time.time() - t0
        data = d["data"]
        return data.get("reply") or data["messages"][-1], time.time() - t0

    r, dt = ask("Cum e vremea sâmbătă? Merită să stau afară?")
    low = (r or {}).get("content", "").lower()
    check("weather answer from the real AI", r and r["provider"] != "local" and any(x in low for x in ("°", "%", "ploa", "ceață", "senin")), f"{r and r['model']} {dt:.0f}s {short(r)}")
    r, dt = ask("E grevă sau vreun protest? Pot lua autobuzul?")
    check("news answer with source links", r and r["provider"] != "local" and any(x.get("type") == "link" for x in r["references"]), f"{dt:.0f}s {short(r)}")
    r, dt = ask("Adaugă cină la Roscioli sâmbătă la 20:00")
    check("adds dinner when asked", r and any(c["name"] == "create_itinerary_event" and c["status"] == "ok" for c in r["tool_calls"]), f"{dt:.0f}s {short(r)}")
    s, ev = call("GET", f"/trips/{tid}/itinerary")
    added = [e for e in ev["data"] if "oscioli" in e["title"]]
    check("dinner is planned (not a suggestion) and has an end", added and added[0]["status"] == "unbooked" and added[0]["end_local"], str(added and (added[0]["start_local"], added[0]["end_local"])))
    r, dt = ask("Vreau să fac ceva cultural dar nu știu exact ce")
    chips = [x["options"] for x in (r or {}).get("references", []) if x["type"] == "choices"]
    check("asks a clarifying question with answers, or searches", r and (chips or any(c["name"] == "search_activities" for c in r["tool_calls"])), f"{'CHIPS ' + str(chips[0]) if chips else 'searched'} {dt:.0f}s")
    r, dt = ask(chips[0][0] if chips else "Muzee")
    cards = [x for x in (r or {}).get("references", []) if x["type"] == "activity"]
    check("the tapped answer leads to results", r and (cards or any(c["name"] == "search_activities" for c in r["tool_calls"])), f"{len(cards)} cards {dt:.0f}s {short(r)}")
    r, dt = ask("Cum ajung de la Craiova la Roma cu avionul pe 12 noiembrie?")
    check("journey answer", r and (any(c["name"] == "plan_journey" for c in r["tool_calls"]) or "google.com/travel/flights" in r["content"]), f"{dt:.0f}s {short(r)}")
    r, dt = ask("Ce mai am neconfirmat?")
    check("answers from the trip brief", r and r["provider"] != "local", f"{dt:.0f}s {short(r)}")

    s, sm = call("GET", "/demo/samples")
    samples = sm.get("data") or []
    check("sample documents listed", s == 200 and len(samples) >= 2, ", ".join(x["key"] for x in samples))
    s, d = call("POST", f"/demo/samples/{samples[0]['key']}/upload", {}, timeout=90)
    check("sample goes through the reading pipeline", s in (200, 201), str(d)[:120])
    print(f"\n{sum(results)}/{len(results)} passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
