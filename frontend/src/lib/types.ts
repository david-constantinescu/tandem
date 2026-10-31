export type User = {
  id: string;
  email: string;
  display_name: string;
  home_city: string | null;
  home_airport: string | null;
  locale: string;
  timezone: string;
  is_demo: boolean;
};

export type TripDestination = { id: string; name: string; country: string | null; lat: number | null; lon: number | null; timezone: string | null; arrive_date: string | null; depart_date: string | null };

export type ItineraryEvent = {
  id: string;
  trip_id: string;
  reservation_id: string | null;
  type: string;
  status: "confirmed" | "pending" | "suggested" | "unbooked" | "cancelled" | "completed";
  title: string;
  notes: string;
  start_at: string;
  start_tz: string;
  start_local: string;
  end_at: string | null;
  end_tz: string | null;
  end_local: string | null;
  location_name: string | null;
  address: string | null;
  city: string | null;
  lat: number | null;
  lon: number | null;
  end_location_name: string | null;
  end_city: string | null;
  source: string;
  details: Record<string, any>;
};

export type Trip = {
  id: string;
  name: string;
  start_date: string | null;
  end_date: string | null;
  primary_destination: string | null;
  notes: string;
  is_cancelled: boolean;
  created_via: string;
  grouping: Record<string, any>;
  destinations: TripDestination[];
  travellers: { id: string; full_name: string; is_primary: boolean }[];
  stats: {
    reservations?: number;
    documents?: number;
    phase?: "planning" | "upcoming" | "current" | "past" | "cancelled";
    reservation_types?: Record<string, number>;
    next_event?: ItineraryEvent | null;
    conflict_count?: number;
  };
};

export type ReservationChange = { id: string; reservation_id: string; changes: Record<string, { old: any; new: any }>; status: string; summary: string; detected_at: string; source_document_id: string | null };

export type Reservation = {
  id: string;
  trip_id: string | null;
  type: string;
  status: "confirmed" | "pending" | "cancelled" | "unknown";
  title: string;
  provider_name: string | null;
  booking_reference: string | null;
  origin: string | null;
  destination: string | null;
  start_local: string | null;
  start_tz: string | null;
  end_local: string | null;
  end_tz: string | null;
  location_name: string | null;
  address: string | null;
  city: string | null;
  price: number | null;
  currency: string | null;
  travellers: string[];
  details: Record<string, any>;
  cancellation_deadline: string | null;
  cancellation_policy: string | null;
  source_document_id: string | null;
  confidence: number | null;
  verification: "verified" | "user_confirmed" | "unverified";
  created_via: string;
  changes?: ReservationChange[];
};

export type ExtractedField = { field: string; value: any; evidence: string | null; confidence: number | null; source_page: number | null; verification: string };

export type ExtractedRecord = {
  id: string;
  document_id: string;
  record_type: string;
  data: Record<string, any>;
  confidence: number;
  uncertainty_notes: string[];
  status: "pending_review" | "accepted" | "rejected" | "change_detected";
  extractor: { provider?: string; model?: string; path?: string };
  grouping: { action?: "join" | "create"; applied?: { trip_id?: string }; trip_id?: string; trip_name?: string; score?: number; reasons?: string[]; new_trip?: { name: string; destination: string | null; start_date: string | null; end_date: string | null } };
  matched_reservation_id: string | null;
  reservation_id: string | null;
  fields: ExtractedField[];
};

export type DocumentItem = {
  id: string;
  trip_id: string | null;
  parent_document_id: string | null;
  duplicate_of_id: string | null;
  source: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  status: string;
  status_detail: string;
  classification: string | null;
  page_count: number | null;
  source_url: string | null;
  extraction_method: { path?: string; provider?: string; model?: string; attempts?: { path: string; ok: boolean; reason?: string; provider?: string }[] };
  has_original: boolean;
  created_at: string;
  processed_at: string | null;
  record_count: number;
  pending_review_count: number;
  records?: ExtractedRecord[];
  attachments?: DocumentItem[];
  extracted_text?: string | null;
};

export type Conflict = { type: string; severity: "critical" | "warning" | "info"; title: string; detail: string; event_ids: string[]; reservation_ids: string[]; key: string };

export type Action = {
  id: string;
  trip_id: string | null;
  conversation_id: string | null;
  action_type: string;
  provider: string | null;
  status: string;
  title: string;
  description: string;
  payload: Record<string, any>;
  payload_hash: string;
  cost: number | null;
  currency: string | null;
  consequences: string[];
  cancellation_policy: string | null;
  external: boolean;
  created_by: string;
  expires_at: string | null;
  result: Record<string, any>;
  error: string | null;
  executed_at: string | null;
  created_at: string;
};

export type ActivityResult = {
  provider: string;
  provider_item_id: string;
  title: string;
  description: string;
  image_url: string | null;
  location_name: string | null;
  address: string | null;
  city: string | null;
  lat: number | null;
  lon: number | null;
  price: number | null;
  currency: string | null;
  price_basis: string | null;
  duration_minutes: number | null;
  categories: string[];
  rating: number | null;
  review_count: number | null;
  booking_url: string | null;
  cancellation_policy: string | null;
  availability_checked: boolean;
  available_slots: { date: string; time: string; remaining: number; timezone?: string }[];
  bookable_via_api: boolean;
  accessible: boolean | null;
  opening_hours_text: string | null;
  source_label: string;
  attribution: string | null;
  simulated: boolean;
  distance_km: number | null;
  weather_note?: "outdoor_in_bad_weather" | "indoor_good_for_rain" | null;
  fits: { status?: "fits" | "no_fitting_slot" | "availability_unknown"; slots?: { date: string; time: string; end_time: string; remaining: number }[]; free_windows?: Record<string, { start: string; end: string; minutes: number }[]> };
};

export type ProviderCaps = { key: string; name: string; state: string; search: boolean; details: boolean; availability: boolean; booking: boolean; redirect: boolean; simulated: boolean; environment: string | null; notes: string[]; docs_url: string | null };

export type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  tool_calls: { name: string; status: string; permission: string; summary: string }[];
  references: { type: string; id: string; label: string; url?: string; options?: string[]; trip_id?: string; activity?: Partial<ActivityResult>; date?: string | null }[];
  action_ids: string[];
  provider: string | null;
  model: string | null;
  created_at: string;
};

export type Conversation = { id: string; trip_id: string | null; title: string; created_at: string; updated_at: string };

export type Notification = { id: string; type: string; severity: "info" | "warning" | "critical" | "success"; title: string; body: string; link: string | null; read: boolean; created_at: string };

export type BookingSite = {
  key: string;
  name: string;
  category: "train" | "bus" | "flight" | "museum" | "gallery" | "attraction";
  homepage: string;
  country: string;
  simulated: boolean;
  terms_note: string;
  automation_forbidden: boolean;
  notes: string[];
  policy: "simulated" | "assisted" | "link_only";
  agent_can: { search: boolean; select: boolean; enter_traveller_details: boolean; payment: string; deep_link: boolean };
};

export type BrowserStep = { step: number; action: string; reason: string; at: string; url: string | null; title: string | null; screenshot?: string; page_text?: string };

export type BrowserTask = {
  id: string;
  site: string;
  site_name: string;
  simulated: boolean;
  state: string;
  goal: string;
  params: Record<string, any>;
  engine: string | null;
  stop_reason: string | null;
  handoff_url: string | null;
  result: { offers?: { offer_id?: string; title?: string; depart?: string; arrive?: string; total?: number; price?: number; currency?: string }[]; selected?: any; selection_reason?: string; reservation_id?: string; confirmation?: Record<string, string>; venue_name?: string };
  log: BrowserStep[];
  action_id: string | null;
  trip_id: string | null;
  created_at: string;
};

export type DayWeather = {
  date: string; condition: "clear" | "cloudy" | "fog" | "drizzle" | "rain" | "snow" | "storm" | "unknown";
  temp_max: number | null; temp_min: number | null; precip_probability: number | null; precip_mm: number | null;
  wind_kmh: number | null; wet_hours: string[]; outdoor_ok: boolean;
};
export type NewsItem = { title: string; url: string; source: string; published: string | null; kind: "strike" | "protest" | "weather" | "closure" | "news"; mentions_dates: string[] };
export type TripContext = {
  weather: { available: boolean; reason?: string; forecast_from?: string; source?: string; place?: string | null; days: DayWeather[] };
  news: { available: boolean; reason?: string; source?: string; place?: string | null; items: NewsItem[] };
};
export type JourneyLink = { kind: "planner" | "operator"; name: string; url: string; covers: string; official?: boolean; automation_forbidden?: boolean };
