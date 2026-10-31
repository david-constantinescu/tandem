"""interfata pt provideri de activitati si starile lor"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date

# capability states shown in the UI. A provider must never look more capable than its state.
NOT_CONFIGURED = "not_configured"
CONFIGURATION_REQUIRED = "configuration_required"
AWAITING_PARTNER_APPROVAL = "awaiting_partner_approval"
SANDBOX_ONLY = "sandbox_only"
SEARCH_ONLY = "search_only"
SEARCH_AND_AVAILABILITY = "search_and_availability"
REDIRECT_ONLY = "redirect_only"
BOOKING_ENABLED = "booking_enabled"
MANAGEMENT_ENABLED = "management_enabled"
TEMPORARILY_UNAVAILABLE = "temporarily_unavailable"
DISABLED = "disabled"
SIMULATED = "simulated_demo"

OPERATIONAL_STATES = {SANDBOX_ONLY, SEARCH_ONLY, SEARCH_AND_AVAILABILITY, REDIRECT_ONLY, BOOKING_ENABLED,
                      MANAGEMENT_ENABLED, SIMULATED}


class ProviderCapabilityError(Exception):
    def __init__(self, message: str, code: str = "unsupported_operation"):
        super().__init__(message)
        self.code = code


class ProviderRequestError(Exception):
    def __init__(self, message: str, code: str = "provider_error", retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


@dataclass
class ActivitySearchRequest:
    location: str | None = None
    lat: float | None = None
    lon: float | None = None
    date_from: date | None = None
    date_to: date | None = None
    start_after: str | None = None  # HH:MM local
    end_before: str | None = None  # HH:MM local
    max_price: float | None = None
    currency: str = "EUR"
    categories: list[str] = field(default_factory=list)
    query: str | None = None
    group_size: int = 1
    max_duration_minutes: int | None = None
    accessible_only: bool = False
    radius_km: float = 4.0
    limit: int = 20


@dataclass
class ActivityResult:
    provider: str
    provider_item_id: str
    title: str
    description: str = ""
    image_url: str | None = None
    location_name: str | None = None
    address: str | None = None
    city: str | None = None
    lat: float | None = None
    lon: float | None = None
    price: float | None = None
    currency: str | None = None
    price_basis: str | None = None  # per_person | per_group | free
    duration_minutes: int | None = None
    categories: list[str] = field(default_factory=list)
    rating: float | None = None
    review_count: int | None = None
    booking_url: str | None = None
    cancellation_policy: str | None = None
    availability_checked: bool = False
    available_slots: list[dict] = field(default_factory=list)  # [{date, time, remaining}]
    bookable_via_api: bool = False
    accessible: bool | None = None
    opening_hours_text: str | None = None
    source_label: str = ""
    attribution: str | None = None
    simulated: bool = False
    distance_km: float | None = None
    fits: dict = field(default_factory=dict)  # itinerary-fit analysis (filled by the search service)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AvailabilityQuote:
    provider: str
    provider_item_id: str
    title: str
    date: str
    time: str
    participants: int
    available: bool
    unit_price: float | None
    total_price: float | None
    currency: str | None
    cancellation_policy: str | None
    duration_minutes: int | None
    timezone: str | None
    quote_ref: str | None = None
    checked_at: str | None = None
    detail: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class BookingResult:
    provider_booking_id: str
    status: str  # confirmed | pending | failed | cancelled
    simulated: bool = False
    voucher_url: str | None = None
    summary: dict = field(default_factory=dict)


class TravelProviderAdapter:
    key = "base"
    name = "Base"
    docs_url: str | None = None
    simulated = False

    def __init__(self, cfg):
        self.cfg = cfg

    def state(self) -> str:
        return NOT_CONFIGURED

    def capabilities(self) -> dict:
        return {"key": self.key, "name": self.name, "state": self.state(), "search": False, "details": False,
                "availability": False, "booking": False, "cancellation": False, "redirect": False,
                "simulated": self.simulated, "environment": None, "notes": [], "docs_url": self.docs_url}

    def operational(self) -> bool:
        return self.state() in OPERATIONAL_STATES

    def health_check(self) -> dict:
        return {"state": self.state()}

    def search(self, req: ActivitySearchRequest) -> list[ActivityResult]:
        raise ProviderCapabilityError(f"{self.name} search is not available ({self.state()})")

    def get_details(self, item_id: str) -> ActivityResult:
        raise ProviderCapabilityError(f"{self.name} does not provide activity details ({self.state()})")

    def check_availability(self, item_id: str, day: str, time: str | None, participants: int) -> AvailabilityQuote:
        raise ProviderCapabilityError(f"{self.name} does not provide live availability ({self.state()})")

    def create_booking(self, quote: dict, traveller: dict, idempotency_key: str) -> BookingResult:
        raise ProviderCapabilityError(f"Booking through {self.name} is not enabled ({self.state()})")

    def get_booking(self, booking_id: str) -> BookingResult:
        raise ProviderCapabilityError(f"{self.name} booking retrieval is not enabled")

    def modify_booking(self, booking_id: str, changes: dict) -> BookingResult:
        raise ProviderCapabilityError(f"{self.name} does not support booking changes")

    def cancel_booking(self, booking_id: str) -> BookingResult:
        raise ProviderCapabilityError(f"{self.name} cancellation is not enabled")
