# Airline integrations

Airline work is Phase 4 and is separated into three capabilities. Only the first is implemented.

## A. Existing booking import — implemented

Flight confirmations arrive by upload (PDF, screenshot, photo), paste, link or Gmail. Extraction
captures airline, flight number, departure/arrival airports (IATA codes resolved offline via
`airportsdata`), local departure/arrival times with each airport's IANA zone, passengers, booking
reference, ticket number, seat, baggage, terminal, gate and status. Multi-segment itineraries
become one record per flight. Overnight and cross-timezone flights are handled (UTC storage, local
display, next-day arrival inference flagged as a note). Airline schedule-change emails update the
existing reservation through the change-detection flow (diff → user applies → history kept).

## B. Flight search — not implemented

There is no public consumer flight-search API from the airlines below. Options for later:
authorised distribution (NDC aggregators / GDS via an accredited partner) or metasearch affiliate
programmes. Tandem will not scrape airline websites or invent availability.

## C. Booking and management — not implemented

Direct booking, changes or cancellation require an authorised API (airline NDC programme with
agency accreditation, or an aggregator). Until then Tandem offers official link-outs:

| Airline | Developer / partner route (to investigate with a business account) | Consumer link-out |
|---|---|---|
| American Airlines | NDC programme for accredited agencies; no public consumer booking API | https://www.aa.com |
| Lufthansa Group | Lufthansa Open API (schedules/status for registered developers); NDC for partners | https://www.lufthansa.com |
| British Airways | NDC via accredited partners | https://www.britishairways.com |
| Air France–KLM | Air France-KLM developer portal (offers/flight status for partners); NDC | https://www.airfrance.com · https://www.klm.com |
| Ryanair | No public partner API; distribution via selected OTA agreements | https://www.ryanair.com |
| Wizz Air | No public partner API | https://wizzair.com |

Rules that will apply to any airline workflow: no CAPTCHA/MFA/anti-bot bypass, no stored airline
passwords in plaintext, no booking claimed until the airline or authorised provider confirms it.

## Flight status monitoring

Not implemented. Candidate approach: a licensed flight-status API behind the provider adapter
pattern, feeding the existing reservation-change flow (delays become pending changes the user applies).
