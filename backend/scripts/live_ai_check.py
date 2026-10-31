"""Live check of the whole assistant against the real AI providers and real weather/news/journey sources.

Not part of the test suite (it spends free-tier quota and needs the network). Run it with the keys in the
environment, against a throwaway PostgreSQL database:

    set -a; . ../.env.production.local; set +a
    TEST_DATABASE_URL=postgresql+psycopg://tandem@127.0.0.1:5433/tandem_test python scripts/live_ai_check.py

It prints, for every scripted turn, the tools the model called and its reply, then a pass/fail summary.
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import ItineraryEvent, Trip  # noqa: E402
from app.services.agent import orchestrator  # noqa: E402
from app.services.demo.seed import create_demo_workspace  # noqa: E402

DB = os.environ.get("TEST_DATABASE_URL", "postgresql+psycopg://tandem@127.0.0.1:5433/tandem_test")

# (what the user says, tools that must have been called, a check on the reply/state)
SCRIPT = [
    ("Cum e vremea sâmbătă? Merită să stau afară?", set(), "weather"),
    ("E grevă sau vreun protest? Pot lua autobuzul?", {"check_local_news"}, None),
    ("Adaugă cină la Roscioli sâmbătă la 19:30", {"create_itinerary_event"}, "dinner"),
    ("Vreau să fac ceva cultural dar nu știu exact ce", set(), "ask_or_search"),
    ("Un tur ghidat", {"search_activities"}, None),
    ("Cum ajung de la Craiova la Roma cu avionul pe 12 noiembrie?", {"plan_journey"}, None),
    ("Ce mai am neconfirmat?", set(), "confirmed"),
]


def main() -> int:
    if not os.environ.get("GEMINI_API_KEY"):
        print("GEMINI_API_KEY is not set")
        return 2
    app = create_app({"SQLALCHEMY_DATABASE_URI": DB, "JOB_RUNNER": "inline", "RATELIMIT_ENABLED": False,
                      "LOCATION_PROVIDER": "offline", "OSM_PLACES_ENABLED": True, "WEATHER_ENABLED": True,
                      "NEWS_ENABLED": True, "DEMO_ALLOW_EXTERNAL_AI": True,
                      "SECRET_KEY": "live-check-secret-key-long-enough-1234567890"})
    failures = 0
    with app.app_context():
        db.drop_all()
        db.create_all()
        user = create_demo_workspace(locale="ro")
        user.ai_settings.mode = "full"
        db.session.commit()
        trip = db.session.execute(db.select(Trip).where(Trip.user_id == user.id)).scalars().first()
        conv = orchestrator.Conversation(user_id=user.id, trip_id=trip.id, title="New conversation")
        db.session.add(conv)
        db.session.commit()
        for text, expect_tools, check in SCRIPT:
            started = time.monotonic()
            msg = orchestrator.respond(user, conv, text)
            called = {c["name"] for c in msg.tool_calls}
            ok = expect_tools <= called and msg.provider != "local"
            low = msg.content.lower()
            if check == "weather":
                ok = ok and ("°" in msg.content or "%" in msg.content or "ploa" in low or "senin" in low or "ceață" in low)
            if check == "dinner":
                e = db.session.execute(db.select(ItineraryEvent).where(ItineraryEvent.title.ilike("%roscioli%"))).scalars().first()
                ok = ok and e is not None and e.status == "unbooked" and e.end_at is not None
                ok = ok and ("suprap" in low or "overlap" in low)  # it told the user about the clash
            if check == "ask_or_search":
                asked = any(r["type"] == "choices" for r in msg.references)
                print("  (asked a clarifying question with chips)" if asked else "  (went straight to searching)")
                ok = ok and (asked or "search_activities" in called)
            if check == "confirmed":
                ok = ok and "confirm" in low
            failures += not ok
            print(f"\n{'PASS' if ok else 'FAIL'}  [{time.monotonic() - started:.1f}s] {msg.provider}/{msg.model}  {text}")
            print("  tools:", [(c["name"], c["status"]) for c in msg.tool_calls])
            print("  reply:", msg.content[:600].replace("\n", "\n         "))
        db.session.remove()
    print(f"\n{len(SCRIPT) - failures}/{len(SCRIPT)} turns passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
