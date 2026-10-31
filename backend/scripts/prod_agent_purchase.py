"""Live: ask the assistant to buy a Wizz Air flight, then follow the agent through both approvals on the practice
airline. Prints every step. Uses the real AI (free quota) and production by default."""
from __future__ import annotations

import importlib.util
import os
import sys
import time

spec = importlib.util.spec_from_file_location("e2e", os.path.join(os.path.dirname(__file__), "prod_e2e.py"))
e2e = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e2e)


def main() -> int:
    s, d = e2e.call("POST", "/auth/demo", {})
    e2e.csrf = (d.get("data") or {}).get("csrf_token") or (d.get("meta") or {}).get("csrf_token", "")
    s, d = e2e.call("GET", "/trips")
    trip = d["data"][0]
    s, d = e2e.call("POST", "/assistant/conversations", {"trip_id": trip["id"]})
    cid = d["data"]["id"]

    def say(text):
        t0 = time.time()
        s, d = e2e.call("POST", f"/assistant/conversations/{cid}/messages", {"content": text})
        if s not in (200, 201):
            print("HTTP", s, str(d)[:200])
            return None, None
        data = d["data"]
        r = data.get("reply") or data["messages"][-1]
        print(f"\n> {text}\n[{time.time() - t0:.0f}s {r['provider']}/{r['model']}] tools={[c['name'] for c in r['tool_calls']]}")
        print("  " + r["content"][:500].replace("\n", "\n  "))
        links = [x.get("url") for x in r["references"] if x["type"] == "link"]
        chips = [x["options"] for x in r["references"] if x["type"] == "choices"]
        if links:
            print("  links:", links[:3])
        if chips:
            print("  chips:", chips[0])
        return r, data

    r, _ = say(f"Cumpără-mi un zbor Wizz Air de la Craiova la Roma pe {trip['start_date']} pentru 2 persoane")
    chips = [x["options"] for x in (r or {}).get("references", []) if x["type"] == "choices"]
    yes = next((o for o in (chips[0] if chips else []) if any(w in o.lower() for w in ("da", "yes", "exers", "practic", "arat"))), None)
    r, data = say(yes or "Da, arată-mi tot procesul pe compania de exerciții")
    actions = (data or {}).get("actions", {})
    pending = [a for a in actions.values() if a["status"] == "awaiting_approval"]
    if not pending:
        print("\nNo approval card yet: FAIL")
        return 1
    a = pending[0]
    print(f"\nAPPROVAL 1: {a['title']} — {a['action_type']} — {a['consequences']}")
    s, first = e2e.call("POST", f"/approvals/{a['id']}/approve", {"payload_hash": a["payload_hash"]})
    print("  ->", first["data"]["status"], first["data"].get("result"))
    pay_id = first["data"]["result"]["payment_action_id"]
    s, pay = e2e.call("GET", f"/approvals/{pay_id}")
    pay = pay["data"]
    print(f"APPROVAL 2: {pay['title']} — {pay['action_type']} — {pay['consequences']}")
    s, task = e2e.call("GET", f"/browser/tasks/{a['payload']['task_id']}")
    print("  agent steps so far:", [st["action"] for st in task["data"]["log"]])
    s, done = e2e.call("POST", f"/approvals/{pay_id}/approve", {"payload_hash": pay["payload_hash"]})
    print("  ->", done["data"]["status"], done["data"].get("result"))
    s, task = e2e.call("GET", f"/browser/tasks/{a['payload']['task_id']}")
    print("  agent steps:", [st["action"] for st in task["data"]["log"]], task["data"]["state"])
    s, res = e2e.call("GET", f"/trips/{trip['id']}/reservations")
    ref = done["data"]["result"].get("provider_booking_id")
    booked = [x for x in res["data"] if x["booking_reference"] == ref]
    print("  in the trip:", booked and (booked[0]["title"], booked[0]["travellers"], booked[0]["start_local"]))
    ok = done["data"]["status"] == "completed" and bool(booked)
    print("\nPASS" if ok else "\nFAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
