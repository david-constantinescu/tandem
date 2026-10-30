"""Offline assistant used when no AI provider may or can be used.

It recognises a handful of common requests and answers them from the same permission-checked tools
the AI agent uses, so the answers come from real trip data. It says clearly that it is running in a
limited offline mode.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from app.services.agent.tools import ToolContext, _next_trip, run_tool, today_for
from app.services.ingestion.dates import find_dates

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
CATEGORY_WORDS = {"museum": "museums", "gallery": "museums", "tour": "tours", "walking": "tours", "food": "food",
                  "eat": "food", "cooking": "workshops", "workshop": "workshops", "class": "workshops",
                  "outdoor": "outdoor", "bike": "outdoor", "history": "historical", "historic": "historical",
                  "show": "entertainment", "nightlife": "entertainment", "day trip": "day trips"}


def _fmt_time(iso_value: str | None) -> str:
    if not iso_value:
        return ""
    return datetime.fromisoformat(iso_value).strftime("%a %d %b %H:%M")


def _resolve_day(text: str, user, trip_start: date | None, trip_end: date | None) -> date | None:
    t = text.lower()
    today = today_for(user)
    if "tomorrow" in t:
        return today + timedelta(days=1)
    if "today" in t or "tonight" in t:
        return today
    hits = find_dates(text)
    if hits:
        return hits[0].value
    m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b", t)
    if m:
        month = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"].index(m.group(2)) + 1
        year = today.year if month >= today.month else today.year + 1
        try:
            return date(year, month, int(m.group(1)))
        except ValueError:
            return None
    for i, name in enumerate(WEEKDAYS):
        if name in t:
            start = trip_start if trip_start and trip_start > today else today
            for offset in range(0, 14):
                d = start + timedelta(days=offset)
                if d.weekday() == i and (trip_end is None or d <= trip_end or offset >= 7):
                    return d
    return None


def answer(user, ctx: ToolContext, text: str, tool_log: list, *, reason: str) -> str:
    lower = text.lower()
    header = f"_Offline assistant — {reason}. I can answer common questions from your trip data._\n\n"

    def call(name: str, **kwargs):
        status, result = run_tool(ctx, name, kwargs)
        tool_log.append({"name": name, "status": status, "permission": "read", "args": kwargs,
                         "summary": "Done" if status == "ok" else str(result.get("error"))})
        return result if status == "ok" else None

    trip = _next_trip(user) if not ctx.default_trip_id else None
    trip_info = call("get_trip", trip_id=str(ctx.default_trip_id) if ctx.default_trip_id else (str(trip.id) if trip else None)) \
        if (ctx.default_trip_id or trip) else None
    if not trip_info:
        return header + "You don't have any trips yet. Upload a booking confirmation in the Inbox to get started."
    tid = trip_info["trip_id"]
    t_start = date.fromisoformat(trip_info["start_date"]) if trip_info.get("start_date") else None
    t_end = date.fromisoformat(trip_info["end_date"]) if trip_info.get("end_date") else None

    if re.search(r"unconfirm|not confirmed|pending|still need to book", lower):
        res = call("get_reservations", trip_id=tid) or []
        open_items = [r for r in res if r["status"] != "confirmed"]
        if not open_items:
            return header + f"Everything booked for **{trip_info['name']}** shows as confirmed."
        lines = [f"- **{r['title']}** — {r['status']}" + (f", {_fmt_time(r['start_local'])}" if r["start_local"] else "")
                 for r in open_items]
        return header + f"Not confirmed yet on **{trip_info['name']}**:\n" + "\n".join(lines)

    if re.search(r"conflict|clash|overlap|problem|issue|enough time|tight", lower):
        items = call("detect_conflicts", trip_id=tid) or []
        if not items:
            return header + "I didn't find any conflicts in this itinerary."
        lines = [f"- **{c['title']}** ({c['severity']}): {c['detail']}" for c in items[:8]]
        return header + f"I found {len(items)} item(s) to look at:\n" + "\n".join(lines)

    if re.search(r"find|suggest|recommend|something to do|activity|activities|museum|tour|things to do", lower):
        day = _resolve_day(text, user, t_start, t_end)
        cats = sorted({c for w, c in CATEGORY_WORDS.items() if w in lower})
        result = call("search_activities", trip_id=tid, date=day.isoformat() if day else None, categories=cats)
        if not result or not result["results"]:
            unavailable = [p["name"] for p in (result or {}).get("providers", []) if p.get("error")]
            return header + "I couldn't find activities for that." + (
                f" Unavailable providers: {', '.join(unavailable)}." if unavailable else "")
        lines = []
        for r in result["results"][:5]:
            price = f"{r['price']:.0f} {r['currency']}" if r.get("price") is not None and r.get("currency") else "price unknown"
            fit = r["fits"].get("status") if r.get("fits") else None
            fit_text = {"fits": "fits your free time", "no_fitting_slot": "no slot fits your plans",
                        "availability_unknown": "availability not checked"}.get(fit, "")
            slots = ", ".join(s["time"] for s in (r.get("fits") or {}).get("slots", [])[:3])
            lines.append(f"- **{r['title']}** · {price}" + (f" · {fit_text}" if fit_text else "")
                         + (f" (e.g. {slots})" if slots else ""))
        when = f" on {day:%A %d %B}" if day else ""
        return header + f"Options{when}:\n" + "\n".join(lines) + \
            "\n\nUse **Prepare booking** on a card to get a live quote you can approve."

    if re.search(r"summar|before (departure|i leave|leaving)|what do i need|checklist|overview", lower):
        res = call("get_reservations", trip_id=tid) or []
        conflicts = call("detect_conflicts", trip_id=tid) or []
        lines = [f"**{trip_info['name']}** · {trip_info.get('start_date')} → {trip_info.get('end_date')}",
                 f"Destinations: {', '.join(trip_info['destinations']) or 'not set'}", ""]
        for r in res:
            ref = f" · ref {r['booking_reference']}" if r.get("booking_reference") else ""
            lines.append(f"- {r['type'].replace('_', ' ').title()}: **{r['title']}** — {_fmt_time(r['start_local'])}{ref} ({r['status']})")
        crit = [c for c in conflicts if c["severity"] in ("critical", "warning")]
        if crit:
            lines += ["", "Needs attention:"] + [f"- {c['title']}" for c in crit[:5]]
        return header + "\n".join(lines)

    if re.search(r"delay", lower):
        it = call("get_itinerary", trip_id=tid) or {"events": []}
        flights = [e for e in it["events"] if e["type"] in ("flight", "train")]
        if not flights:
            return header + "I don't see a flight or train in this trip."
        f = flights[0]
        later = [e for e in it["events"] if e["start_local"] and f["end_local"] and e["start_local"] > f["start_local"]][:4]
        lines = [f"If **{f['title']}** is delayed, the next plans after it are:"] + [
            f"- {e['title']} at {_fmt_time(e['start_local'])}" for e in later if e["event_id"] != f["event_id"]]
        return header + "\n".join(lines) + "\n\nTell me the new arrival time, or upload the airline's update to the Inbox."

    day = _resolve_day(text, user, t_start, t_end)
    if day or re.search(r"booked|plan|schedule|itinerary|what.*(have|doing)", lower):
        it = call("get_itinerary", trip_id=tid, date=day.isoformat() if day else None) or {"events": []}
        events = it["events"]
        if not events:
            return header + (f"Nothing is planned on {day:%A %d %B}." if day else "This trip has no itinerary events yet.")
        title = f"{day:%A %d %B}" if day else trip_info["name"]
        lines = []
        for e in events[:15]:
            status = "" if e["status"] == "confirmed" else f" _({e['status']})_"
            lines.append(f"- {_fmt_time(e['start_local'])} — **{e['title']}**{status}")
        return header + f"**{title}**\n" + "\n".join(lines)

    return header + ("I can tell you what's planned on a day, what's unconfirmed, check conflicts, summarise the "
                     "trip, or find activities that fit your free time. Connect an AI provider in Settings for "
                     "open-ended questions.")
