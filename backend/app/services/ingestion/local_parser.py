"""Rules-based travel document parser that runs entirely on the server.

Used when external AI is disabled, unavailable, or out of quota. It reads labelled fields and common
confirmation layouts (flights, hotels, trains, restaurants, tickets, tours). Results carry lower
confidence than AI extraction and every value keeps the line it was read from as evidence.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.services.geo import find_airport_code, _airports  # noqa: PLC2701 - shared offline airport table
from app.services.ingestion.dates import find_dates, find_times, first_datetime
from app.services.ingestion.schema import ExtractedTravelRecord, ExtractionResult, FieldEvidence, RecordDetails

BASE_CONFIDENCE = 0.5


@dataclass
class Line:
    page: int
    text: str
    offset: int  # offset in the joined text


KEYWORDS: dict[str, list[str]] = {
    "flight": ["flight", "airline", "boarding", "e-ticket", "baggage", "terminal", "gate", "pnr", "airport",
               "departure", "arrival", "itinerary receipt", "cabin"],
    "hotel": ["hotel", "check-in", "check in", "check-out", "check out", "room", "nights", "accommodation",
              "property", "albergo", "hostel", "apartment", "guest house", "b&b", "stay"],
    "train": ["train", "rail", "carriage", "coach ", "platform", "station", "trenitalia", "italo", "eurostar", "sncf"],
    "bus": ["bus ", "coach station", "flixbus", "bus station"],
    "restaurant": ["restaurant", "ristorante", "trattoria", "osteria", "bistro", "table for", "dinner", "lunch",
                   "reservation for", "party of", "brasserie"],
    "museum": ["museum", "musei", "gallery", "galleria", "exhibition", "admission", "timed entry", "entry ticket"],
    "tour": ["tour", "guided", "walking", "meeting point", "your guide", "guide"],
    "activity": ["activity", "experience", "workshop", "class", "cooking", "tasting", "ticket"],
    "car_rental": ["car rental", "car hire", "vehicle", "pick-up location", "drop-off", "rental agreement"],
    "transfer": ["transfer", "shuttle", "private driver", "airport pickup"],
}

REF_LABELS = [
    "booking reference", "booking ref", "booking number", "booking no", "booking code", "booking id",
    "confirmation number", "confirmation code", "confirmation no", "confirmation #", "confirmation",
    "reservation number", "reservation code", "reservation no", "reservation id", "reservation reference",
    "reference number", "reference", "pnr", "record locator", "order number", "order id", "ticket code",
    "voucher number", "voucher code",
]
NAME_LABELS = ["passenger name", "passengers", "passenger", "traveller name", "travellers", "traveller", "traveler",
               "travelers", "guest name", "guests name", "lead traveller", "lead guest", "name", "booked by",
               "reservation name"]
PRICE_LABELS = ["total price", "total paid", "amount paid", "total amount", "grand total", "total", "price",
                "amount charged", "fare"]
CURRENCY_SYMBOLS = {"€": "EUR", "$": "USD", "£": "GBP", "lei": "RON"}
RE_MONEY = re.compile(
    r"(?:(EUR|USD|GBP|RON|CHF|€|\$|£)\s?(\d{1,3}(?:[.,\s]\d{3})*(?:[.,]\d{2})?|\d+(?:[.,]\d{2})?))"
    r"|(?:(\d{1,3}(?:[.,\s]\d{3})*(?:[.,]\d{2})?|\d+(?:[.,]\d{2})?)\s?(EUR|USD|GBP|RON|CHF|€|lei))",
    re.I,
)
RE_FLIGHT = re.compile(r"\b(?:flight|flt|volo)\s*(?:no\.?|number|#)?\s*[:\-]?\s*([A-Z0-9]{2})\s?(\d{1,4})\b", re.I)
RE_TRAIN = re.compile(r"\btrain\s*(?:no\.?|number|#)?\s*[:\-]?\s*([A-Z]{0,4}\s?\d{2,5})\b", re.I)
RE_URL = re.compile(r"https?://[^\s<>\"')]+")
RE_PARTY = re.compile(r"\b(?:table|party|reservation|booking)\s+(?:for|of)\s+(\d{1,2})\b", re.I)
RE_DURATION = re.compile(r"\bduration\s*[:\-]?\s*(\d+(?:[.,]\d+)?)\s*(hours?|hrs?|h|minutes?|mins?)\b", re.I)


class ParsedDoc:
    def __init__(self, text: str):
        self.text = text
        self.lines: list[Line] = []
        page = 1
        offset = 0
        for raw in text.split("\n"):
            m = re.match(r"^\[Page (\d+)\]$", raw.strip())
            if m:
                page = int(m.group(1))
            elif raw.strip():
                self.lines.append(Line(page, raw.strip(), offset))
            offset += len(raw) + 1
        self.lower = text.lower()

    def labeled(self, labels: list[str], *, within: tuple[int, int] | None = None) -> tuple[str, Line] | None:
        for label in labels:
            pattern = re.compile(rf"^\s*{re.escape(label)}\s*(?:\([^)]*\))?\s*[:#\-–]\s*(.+)$", re.I)
            for i, line in enumerate(self.lines):
                if within and not (within[0] <= line.offset < within[1]):
                    continue
                m = pattern.match(line.text)
                if m and m.group(1).strip():
                    return m.group(1).strip(), line
                if line.text.strip().lower().rstrip(":") == label and i + 1 < len(self.lines):
                    return self.lines[i + 1].text.strip(), self.lines[i + 1]
        return None

    def line_at(self, offset: int) -> Line | None:
        found = None
        for line in self.lines:
            if line.offset <= offset:
                found = line
            else:
                break
        return found


def classify(doc: ParsedDoc) -> tuple[str | None, dict[str, int]]:
    scores = {k: sum(doc.lower.count(w) for w in words) for k, words in KEYWORDS.items()}
    if RE_FLIGHT.search(doc.text):
        scores["flight"] += 4
    if re.search(r"check[\s-]?in", doc.lower) and re.search(r"check[\s-]?out", doc.lower):
        scores["hotel"] += 4
    best = max(scores, key=scores.get)
    if scores[best] < 2:
        return None, scores
    # Museums/tours both mention tickets; prefer the more specific signal.
    return best, scores


def parse_text(text: str) -> ExtractionResult:
    # Email send timestamps are not booking dates.
    text = "\n".join(line for line in text.split("\n") if not line.startswith("Sent: "))
    doc = ParsedDoc(text)
    record_type, _ = classify(doc)
    if record_type is None:
        return ExtractionResult(is_travel_related=False, document_summary="No travel booking details recognised")
    common = _common_fields(doc)
    if record_type == "flight":
        records = _flights(doc, common)
    elif record_type == "train":
        records = _trains(doc, common)
    elif record_type == "hotel":
        records = [_hotel(doc, common)]
    else:
        records = [_timed_booking(doc, common, record_type)]
    records = [r for r in records if r is not None]
    if not records:
        return ExtractionResult(is_travel_related=True, records=[],
                                document_summary="Looks travel related, but no bookable details were recognised")
    summary = f"{len(records)} {record_type.replace('_', ' ')} record(s) recognised by the local parser"
    return ExtractionResult(is_travel_related=True, document_summary=summary, records=records)


# ---------------------------------------------------------------------------------------
def _ev(field: str, line: Line | None) -> list[FieldEvidence]:
    return [FieldEvidence(field=field, quote=line.text[:300], page=line.page)] if line else []


def _common_fields(doc: ParsedDoc) -> dict:
    out: dict = {"evidence": [], "notes": []}
    ref = None
    for label in REF_LABELS:
        hit = doc.labeled([label])
        if not hit:
            continue
        m = re.search(r"\b([A-Z0-9][A-Z0-9\-]{3,19})\b", hit[0])
        if m and (re.search(r"\d", m.group(1)) or re.fullmatch(r"[A-Z]{5,8}", m.group(1))):
            ref = m.group(1)
            out["evidence"] += _ev("booking_reference", hit[1])
            break
    out["booking_reference"] = ref

    names: list[str] = []
    hit = doc.labeled(NAME_LABELS)
    if hit:
        for raw in re.split(r",|;| and |&", hit[0]):
            name = re.sub(r"\b(mr|mrs|ms|miss|dr)\.?\s+", "", raw.strip(), flags=re.I)
            name = re.sub(r"\(.*?\)", "", name).strip()
            if 2 <= len(name) <= 80 and re.search(r"[A-Za-z]", name) and not re.search(r"\d", name):
                names.append(name.title() if name.isupper() else name)
        out["evidence"] += _ev("traveller_names", hit[1])
    out["traveller_names"] = names

    price = currency = None
    hit = doc.labeled(PRICE_LABELS)
    candidates = [hit] if hit else []
    for c in candidates:
        m = RE_MONEY.search(c[0])
        if m:
            price, currency = _money(m)
            out["evidence"] += _ev("price", c[1])
            break
    out["price"], out["currency"] = price, currency

    status = "unknown"
    out["is_cancellation_notice"] = bool(re.search(r"\b(has been|was|is) (cancelled|canceled)\b|cancellation confirm", doc.lower))
    if out["is_cancellation_notice"]:
        status = "cancelled"
    elif re.search(r"\b(confirmed|you're booked|you are booked|ticketed|total paid|amount paid|paid in full|"
                   r"payment received|(table|tour|ticket|room|seat)s? booked)\b", doc.lower):
        status = "confirmed"
    elif re.search(r"\b(pending|awaiting confirmation|request received|on request|not yet confirmed)\b", doc.lower):
        status = "pending"
    out["confirmation_status"] = status
    out["is_change_notice"] = bool(re.search(
        r"\b(updated (booking|reservation|confirmation|itinerary)|schedule change|has been (changed|updated|modified)|"
        r"change to your (booking|reservation)|new (time|departure time)|amended)\b", doc.lower))

    policy_line = next((ln for ln in doc.lines if re.search(r"cancel", ln.text, re.I)
                        and re.search(r"free|refund|until|before|non-refundable|no refund", ln.text, re.I)), None)
    out["cancellation_policy"] = policy_line.text[:500] if policy_line else None
    out["cancellation_deadline_local"] = None
    if policy_line:
        dt, _, _ = first_datetime(policy_line.text)
        if dt:
            out["cancellation_deadline_local"] = dt.strftime("%Y-%m-%dT%H:%M")
            out["evidence"] += _ev("cancellation_deadline_local", policy_line)

    url = RE_URL.search(doc.text)
    out["website"] = url.group(0).rstrip(".,") if url else None
    phone = doc.labeled(["phone", "tel", "telephone", "contact"])
    out["contact"] = phone[0][:200] if phone else None
    return out


def _money(m: re.Match) -> tuple[float | None, str | None]:
    sym = m.group(1) or m.group(4)
    amount = m.group(2) or m.group(3)
    currency = CURRENCY_SYMBOLS.get(sym.lower() if sym.lower() == "lei" else sym, sym.upper())
    amount = amount.replace(" ", "")
    if re.search(r"[.,]\d{2}$", amount):
        whole, frac = amount[:-3], amount[-2:]
        amount = re.sub(r"[.,]", "", whole) + "." + frac
    else:
        amount = re.sub(r"[.,]", "", amount)
    try:
        return float(amount), currency
    except ValueError:
        return None, None


def _base(record_type: str, common: dict) -> dict:
    return {
        "record_type": record_type,
        "booking_reference": common["booking_reference"],
        "traveller_names": common["traveller_names"],
        "price": common["price"],
        "currency": common["currency"],
        "confirmation_status": common["confirmation_status"],
        "is_change_notice": common["is_change_notice"],
        "is_cancellation_notice": common["is_cancellation_notice"],
        "cancellation_policy": common["cancellation_policy"],
        "cancellation_deadline_local": common["cancellation_deadline_local"],
        "website": common["website"],
        "contact": common["contact"],
        "evidence": list(common["evidence"]),
        "uncertainty_notes": ["Extracted by Tandem's local rules-based parser (no AI); please review"],
    }


def _confidence(rec: dict) -> float:
    score = BASE_CONFIDENCE
    if rec.get("booking_reference"):
        score += 0.1
    if rec.get("start_local"):
        score += 0.1
    if rec.get("record_type") in ("flight", "train") and rec.get("origin_code") and rec.get("destination_code"):
        score += 0.05
    return round(min(score, 0.75), 2)


def _fmt(dt: datetime | None) -> str | None:
    return dt.strftime("%Y-%m-%dT%H:%M") if dt else None


def _segment_times(doc: ParsedDoc, start: int, end: int) -> tuple[datetime | None, datetime | None, list[str], list[Line]]:
    """Departure and arrival datetimes inside a block, using labels when present."""
    notes: list[str] = []
    lines: list[Line] = []
    dep = arr = None
    dep_hit = doc.labeled(["departure", "departs", "depart", "departure time", "outbound departure"], within=(start, end))
    arr_hit = doc.labeled(["arrival", "arrives", "arrive", "arrival time"], within=(start, end))
    block = doc.text[start:end]
    dates = find_dates(block)
    default_date = dates[0].value if dates else None
    for hit, slot in ((dep_hit, "dep"), (arr_hit, "arr")):
        if not hit:
            continue
        dt, amb, _ = first_datetime(hit[0])
        if dt is None:
            times = find_times(hit[0])
            if times and default_date:
                dt = datetime.combine(default_date, times[0].value)
        if dt is not None and dt.time().hour == 0 and dt.time().minute == 0 and not find_times(hit[0]):
            notes.append(f"No time found for {'departure' if slot == 'dep' else 'arrival'}")
        if amb:
            notes.append(amb)
        lines.append(hit[1])
        if slot == "dep":
            dep = dt
        else:
            arr = dt
    if dep is None and dates:
        dep, amb, _ = first_datetime(block)
        if amb:
            notes.append(amb)
        line = doc.line_at(start + dates[0].start)
        if line:
            lines.append(line)
    if arr is None and dep is not None:
        times = find_times(block)
        later = [t for t in times if datetime.combine(dep.date(), t.value) != dep]
        if later:
            arr = datetime.combine(dep.date(), later[-1].value)
    if dep and arr and arr < dep and arr.date() == dep.date():
        arr += timedelta(days=1)
        notes.append("Arrival time is earlier than departure; assumed next-day arrival")
    return dep, arr, notes, lines


def _flights(doc: ParsedDoc, common: dict) -> list[ExtractedTravelRecord]:
    matches = [m for m in RE_FLIGHT.finditer(doc.text) if re.fullmatch(r"[A-Z0-9]{2}", m.group(1))
               and not m.group(1).isdigit()]
    seen: set[str] = set()
    unique = []
    for m in matches:
        key = f"{m.group(1)}{m.group(2)}"
        if key not in seen:
            seen.add(key)
            unique.append(m)
    airline_hit = doc.labeled(["airline", "operated by", "carrier"])
    seat_hit = doc.labeled(["seat", "seats"])
    bag_hit = doc.labeled(["baggage", "baggage allowance", "checked baggage", "luggage"])
    ticket_hit = doc.labeled(["ticket number", "e-ticket number", "ticket no"])
    cabin_hit = doc.labeled(["cabin", "class", "travel class", "fare type"])
    records = []
    for i, m in enumerate(unique or [None]):
        start = m.start() if m else 0
        end = unique[i + 1].start() if m and i + 1 < len(unique) else len(doc.text)
        block = doc.text[start:end]
        codes = [c for c in re.findall(r"\(([A-Z]{3})\)", block) if c in _airports()]
        if len(codes) < 2:
            codes += [c for c in re.findall(r"\b([A-Z]{3})\b", block) if c in _airports() and c not in codes]
        rec = _base("flight", common)
        if m:
            rec["details"] = {"flight_number": f"{m.group(1)} {m.group(2)}"}
            rec["evidence"] += _ev("flight_number", doc.line_at(m.start()))
        else:
            rec["details"] = {}
        if len(codes) >= 2:
            rec["origin_code"], rec["destination_code"] = codes[0], codes[1]
            for code_field, code in (("origin", codes[0]), ("destination", codes[1])):
                pos = block.find(code)
                line = doc.line_at(start + pos)
                rec[code_field] = _place_text(line.text, code) if line else code
                rec["evidence"] += _ev(f"{code_field}_code", line)
        dep, arr, notes, lines = _segment_times(doc, start, end)
        rec["start_local"], rec["end_local"] = _fmt(dep), _fmt(arr)
        for ln in lines:
            rec["evidence"] += _ev("start_local" if ln is lines[0] else "end_local", ln)
        rec["uncertainty_notes"] += notes
        terminal = re.search(r"\bterminal\s*([A-Z0-9]{1,3})\b", block, re.I)
        details = rec["details"]
        if airline_hit:
            details["airline"] = airline_hit[0][:100]
        if terminal:
            details["terminal"] = terminal.group(1)
        seg_seat = doc.labeled(["seat", "seats"], within=(start, end)) or (seat_hit if len(unique) <= 1 else None)
        if seg_seat:
            details["seat"] = seg_seat[0][:40]
        if bag_hit:
            details["baggage"] = bag_hit[0][:200]
        if ticket_hit:
            details["ticket_number"] = ticket_hit[0][:40]
        if cabin_hit:
            details["cabin_class"] = cabin_hit[0][:40]
        rec["provider_name"] = details.get("airline")
        route = f"{rec.get('origin_code') or '?'} → {rec.get('destination_code') or '?'}"
        rec["title"] = f"Flight {details.get('flight_number', '')} {route}".replace("  ", " ").strip()
        if not rec.get("start_local"):
            rec["uncertainty_notes"].append("Departure date/time not found")
        if len(unique) > 1 and i > 0:
            # Price on a multi-segment confirmation usually covers the whole itinerary.
            rec["price"] = None
        rec["confidence"] = _confidence(rec)
        records.append(ExtractedTravelRecord(**{**rec, "details": RecordDetails(**details)}))
    return records


def _place_text(line: str, code: str) -> str:
    m = re.search(rf"([A-Za-zÀ-ÿ'.\- ]{{3,60}})\s*\({code}\)", line)
    if m:
        name = re.sub(r"^(from|to|departure|arrival|departs|arrives|depart|arrive)\s*[:\-]?\s*", "",
                      m.group(1).strip(), flags=re.I)
        return f"{name} ({code})"
    return code


def _trains(doc: ParsedDoc, common: dict) -> list[ExtractedTravelRecord]:
    m = RE_TRAIN.search(doc.text)
    rec = _base("train", common)
    details: dict = {}
    if m:
        details["train_number"] = m.group(1).strip()
        rec["evidence"] += _ev("train_number", doc.line_at(m.start()))
    origin = doc.labeled(["from", "departure station", "origin", "departs from"])
    dest = doc.labeled(["to", "arrival station", "destination", "arrives at"])
    if origin:
        rec["origin"] = re.split(r"\s{2,}|,|\d{1,2}:\d{2}", origin[0])[0].strip()[:120]
        rec["evidence"] += _ev("origin", origin[1])
    if dest:
        rec["destination"] = re.split(r"\s{2,}|,|\d{1,2}:\d{2}", dest[0])[0].strip()[:120]
        rec["evidence"] += _ev("destination", dest[1])
    dep, arr, notes, lines = _segment_times(doc, 0, len(doc.text))
    rec["start_local"], rec["end_local"] = _fmt(dep), _fmt(arr)
    for ln in lines:
        rec["evidence"] += _ev("start_local" if ln is lines[0] else "end_local", ln)
    rec["uncertainty_notes"] += notes
    for label, key in ((["coach", "carriage"], "carriage"), (["seat", "seats"], "seat")):
        hit = doc.labeled(label)
        if hit:
            details[key] = hit[0][:40]
    operator = doc.labeled(["operator", "operated by", "carrier"])
    rec["provider_name"] = operator[0][:100] if operator else None
    rec["title"] = f"Train {details.get('train_number', '')} {rec.get('origin') or ''} → {rec.get('destination') or ''}".strip()
    rec["confidence"] = _confidence(rec)
    return [ExtractedTravelRecord(**{**rec, "details": RecordDetails(**details)})]


HOTEL_NAME_RE = re.compile(r"\b(hotel|albergo|hostel|resort|inn|suites|residence|apartments?|b&b|guest ?house|palazzo)\b", re.I)


def _hotel(doc: ParsedDoc, common: dict) -> ExtractedTravelRecord:
    rec = _base("hotel", common)
    name_hit = doc.labeled(["hotel", "property", "accommodation", "hotel name", "property name"])
    if name_hit:
        rec["provider_name"] = name_hit[0][:200]
        rec["evidence"] += _ev("provider_name", name_hit[1])
    else:
        line = next((ln for ln in doc.lines[:15] if HOTEL_NAME_RE.search(ln.text) and len(ln.text) < 80
                     and not re.search(r"confirm|booking|reservation", ln.text, re.I)), None)
        if line:
            rec["provider_name"] = line.text
            rec["evidence"] += _ev("provider_name", line)
    details: dict = {}
    for labels, slot in ((["check-in", "check in", "arrival", "arrival date", "check-in date"], "start_local"),
                         (["check-out", "check out", "departure", "departure date", "check-out date"], "end_local")):
        hit = doc.labeled(labels)
        if not hit:
            continue
        dt, amb, time_text = first_datetime(hit[0])
        if dt is None:
            continue
        if time_text is None:
            window = re.search(r"(?:from|after|until|before|by)\s+(\d{1,2}[:h]\d{2}(?:\s*[ap]m)?)", hit[0], re.I)
            if window:
                t = find_times(window.group(1))
                if t:
                    dt = datetime.combine(dt.date(), t[0].value)
                    time_text = window.group(1)
        if time_text is None:
            rec["uncertainty_notes"].append(f"No {'check-in' if slot == 'start_local' else 'check-out'} time printed")
        else:
            details["check_in_from" if slot == "start_local" else "check_out_until"] = dt.strftime("%H:%M")
        if amb:
            rec["uncertainty_notes"].append(amb)
        rec[slot] = _fmt(dt)
        rec["evidence"] += _ev(slot, hit[1])
    addr = doc.labeled(["address", "hotel address", "property address", "location"])
    if addr:
        rec["address"] = addr[0][:400]
        rec["evidence"] += _ev("address", addr[1])
    room = doc.labeled(["room", "room type", "accommodation type", "unit"])
    if room:
        details["room_type"] = room[0][:120]
    nights = re.search(r"\b(\d{1,2})\s+nights?\b", doc.lower)
    if nights:
        details["nights"] = int(nights.group(1))
    guests = re.search(r"\b(\d{1,2})\s+(?:guests?|adults?)\b", doc.lower)
    if guests:
        details["guests"] = int(guests.group(1))
    rec["location_name"] = rec.get("provider_name")
    rec["title"] = rec.get("provider_name") or "Hotel stay"
    rec["confidence"] = _confidence(rec)
    return ExtractedTravelRecord(**{**rec, "details": RecordDetails(**details)})


RESTAURANT_NAME_RE = re.compile(r"\b(osteria|trattoria|ristorante|restaurant|bistro|brasserie|taverna|pizzeria|cafe|café)\b", re.I)

TITLE_LABELS = {
    "restaurant": ["restaurant", "venue", "restaurant name"],
    "museum": ["museum", "attraction", "ticket", "ticket type", "product", "admission", "venue", "experience"],
    "tour": ["tour", "tour name", "activity", "experience", "product", "booking", "event"],
    "activity": ["activity", "experience", "product", "ticket", "event", "class", "workshop"],
    "car_rental": ["vehicle", "car", "car group", "supplier"],
    "transfer": ["transfer", "service", "vehicle"],
    "bus": ["route", "bus", "operator"],
    "event": ["event", "show", "performance"],
}


def _timed_booking(doc: ParsedDoc, common: dict, record_type: str) -> ExtractedTravelRecord:
    rec = _base(record_type, common)
    details: dict = {}
    title_hit = doc.labeled(TITLE_LABELS.get(record_type, ["activity", "event", "booking"]))
    if title_hit:
        rec["title"] = title_hit[0][:200]
        rec["evidence"] += _ev("title", title_hit[1])
    else:
        line = next((ln for ln in doc.lines[:10] if 6 < len(ln.text) < 90
                     and not re.search(r"confirm|thank|dear|hello|booking|reservation|subject|from:|date:", ln.text, re.I)),
                    None)
        rec["title"] = line.text if line else record_type.replace("_", " ").title()
        if line:
            rec["evidence"] += _ev("title", line)
    if record_type == "restaurant" and not title_hit:
        named = next((ln for ln in doc.lines[:12] if RESTAURANT_NAME_RE.search(ln.text) and len(ln.text) < 80
                      and not re.search(r"confirm|thank|dear|subject|from:", ln.text, re.I)), None)
        if named:
            rec["title"] = re.split(r"\s+[-–]\s+", named.text)[-1] if re.search(r"booked|reserved", named.text, re.I) else named.text
    provider = doc.labeled(["operator", "provider", "supplier", "organiser", "organizer", "sold by", "booked with"])
    if provider:
        rec["provider_name"] = provider[0][:200]
    elif record_type == "restaurant":
        rec["provider_name"] = rec["title"]

    when = doc.labeled(["date and time", "date & time", "when", "date", "reservation date", "visit date",
                        "tour date", "event date", "booking date"])
    dt = amb = time_text = None
    if when:
        dt, amb, time_text = first_datetime(when[0])
        if dt:
            rec["evidence"] += _ev("start_local", when[1])
    if dt is None:
        dt, amb, time_text = first_datetime(doc.text)
        if dt:
            first = find_dates(doc.text)[0]
            rec["evidence"] += _ev("start_local", doc.line_at(first.start))
    if dt and time_text is None:
        t_hit = doc.labeled(["start time", "entry time", "time slot", "arrival time", "time", "starts", "start"])
        times = find_times(t_hit[0]) if t_hit else []
        if times:
            dt = datetime.combine(dt.date(), times[0].value)
            rec["evidence"] += _ev("start_local", t_hit[1])
            time_text = times[0].text
    if dt and time_text is None:
        rec["uncertainty_notes"].append("No start time found")
    if amb:
        rec["uncertainty_notes"].append(amb)
    rec["start_local"] = _fmt(dt)

    end_hit = doc.labeled(["end time", "ends", "until", "finishes"])
    if end_hit and dt:
        times = find_times(end_hit[0])
        if times:
            end = datetime.combine(dt.date(), times[0].value)
            rec["end_local"] = _fmt(end if end > dt else end + timedelta(days=1))
            rec["evidence"] += _ev("end_local", end_hit[1])
    if not rec.get("end_local") and dt:
        dur = RE_DURATION.search(doc.text)
        if dur:
            amount = float(dur.group(1).replace(",", "."))
            minutes = amount * 60 if dur.group(2).lower().startswith("h") else amount
            rec["end_local"] = _fmt(dt + timedelta(minutes=minutes))
            rec["evidence"] += _ev("end_local", doc.line_at(dur.start()))
            rec["uncertainty_notes"].append("End time computed from the stated duration")

    addr = doc.labeled(["address", "location", "venue address", "meeting point", "where", "pick-up location"])
    if addr:
        rec["address"] = addr[0][:400]
        rec["evidence"] += _ev("address", addr[1])
    meeting = doc.labeled(["meeting point", "meet at", "meeting location"])
    if meeting:
        details["meeting_point"] = meeting[0][:300]
    party = RE_PARTY.search(doc.text)
    guests = doc.labeled(["guests", "people", "party size", "participants", "travellers", "number of guests",
                          "tickets", "adults"])
    if party:
        details["party_size"] = int(party.group(1))
    elif guests:
        n = re.search(r"\d{1,2}", guests[0])
        if n:
            details["party_size"] = int(n.group(0))
    rec["location_name"] = rec.get("provider_name") if record_type == "restaurant" else (
        rec.get("title") if record_type == "museum" else None)
    rec["confidence"] = _confidence(rec)
    return ExtractedTravelRecord(**{**rec, "details": RecordDetails(**details)})


def airport_code_in(text: str) -> str | None:
    return find_airport_code(text)
