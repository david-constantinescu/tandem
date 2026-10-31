import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";
import type {
  Action, Conflict, Conversation, DocumentItem, ItineraryEvent, Message, Notification, ProviderCaps, Reservation, Trip, TripContext,
} from "./types";

const PROCESSING = new Set(["uploaded", "validating", "queued", "processing", "analysing"]);

export const keys = {
  trips: ["trips"] as const,
  trip: (id: string) => ["trip", id] as const,
  itinerary: (id: string) => ["trip", id, "itinerary"] as const,
  reservations: (id: string) => ["trip", id, "reservations"] as const,
  conflicts: (id: string) => ["trip", id, "conflicts"] as const,
  tripDocs: (id: string) => ["trip", id, "documents"] as const,
  inbox: ["inbox"] as const,
  inboxItem: (id: string) => ["inbox", id] as const,
  approvals: ["approvals"] as const,
  notifications: ["notifications"] as const,
  conversations: ["conversations"] as const,
  conversation: (id: string) => ["conversation", id] as const,
  settings: ["settings"] as const,
};

export function useTrips() {
  return useQuery({ queryKey: keys.trips, queryFn: () => api.get<Trip[]>("/trips") });
}

export function useTrip(id: string) {
  return useQuery({ queryKey: keys.trip(id), queryFn: () => api.get<Trip>(`/trips/${id}`), enabled: !!id });
}

export function useItinerary(id: string) {
  return useQuery({ queryKey: keys.itinerary(id), queryFn: () => api.get<ItineraryEvent[]>(`/trips/${id}/itinerary`), enabled: !!id });
}

export function useReservations(id: string) {
  return useQuery({ queryKey: keys.reservations(id), queryFn: () => api.get<Reservation[]>(`/trips/${id}/reservations`), enabled: !!id });
}

/** Weather for the trip's days and local disruption news; changes slowly, so it's cached for half an hour. */
export function useTripContext(id: string) {
  return useQuery({ queryKey: ["trip", id, "context"], queryFn: () => api.get<TripContext>(`/trips/${id}/context`), enabled: !!id, staleTime: 30 * 60_000 });
}

export function useConflicts(id: string) {
  return useQuery({ queryKey: keys.conflicts(id), queryFn: () => api.get<Conflict[]>(`/trips/${id}/conflicts`), enabled: !!id });
}

export function useTripDocuments(id: string) {
  return useQuery({ queryKey: keys.tripDocs(id), queryFn: () => api.get<DocumentItem[]>(`/trips/${id}/documents`), enabled: !!id });
}

export function useInbox() {
  return useQuery({
    queryKey: keys.inbox,
    queryFn: () => api.getWithMeta<DocumentItem[]>("/inbox"),
    refetchInterval: (q) => (q.state.data?.data.some((d) => PROCESSING.has(d.status) || d.attachments?.some((a) => PROCESSING.has(a.status))) ? 1500 : false),
  });
}

export function useInboxItem(id: string) {
  return useQuery({
    queryKey: keys.inboxItem(id),
    queryFn: () => api.get<DocumentItem>(`/inbox/${id}`),
    enabled: !!id,
    refetchInterval: (q) => (q.state.data && PROCESSING.has(q.state.data.status) ? 1200 : false),
  });
}

export function useApprovals(status?: string) {
  return useQuery({
    queryKey: [...keys.approvals, status ?? "all"],
    queryFn: () => api.get<Action[]>(`/approvals${status ? `?status=${status}` : ""}`),
    refetchInterval: (q) => (q.state.data?.some((a) => a.status === "in_progress") ? 1200 : false),
  });
}

export function useNotifications() {
  return useQuery({
    queryKey: keys.notifications,
    queryFn: () => api.getWithMeta<Notification[]>("/notifications"),
    refetchInterval: 20000,
  });
}

export function useConversations() {
  return useQuery({ queryKey: keys.conversations, queryFn: () => api.get<Conversation[]>("/assistant/conversations") });
}

export type ConversationPayload = { conversation: Conversation; messages: Message[]; actions: Record<string, Action>; reply?: Message };

export function useConversation(id: string | undefined) {
  return useQuery({
    queryKey: keys.conversation(id ?? ""),
    queryFn: () => api.get<ConversationPayload>(`/assistant/conversations/${id}`),
    enabled: !!id,
    refetchInterval: (q) => {
      const data = q.state.data;
      if (Object.values(data?.actions ?? {}).some((a) => a.status === "in_progress")) return 1500;
      // Just added a file that Tandem is still reading: look again shortly for its follow-up.
      const last = data?.messages[data.messages.length - 1];
      const fresh = last && last.model === "reader" && Date.now() - new Date(last.created_at).getTime() < 90_000;
      return fresh ? 4000 : false;
    },
  });
}

export function useActivityProviders() {
  return useQuery({ queryKey: ["activity-providers"], queryFn: () => api.get<ProviderCaps[]>("/activities/providers"), staleTime: 60000 });
}

/** Invalidate everything that a trip-changing mutation can affect. */
export function useInvalidateTripData() {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: ["trip"] });
    qc.invalidateQueries({ queryKey: keys.trips });
    qc.invalidateQueries({ queryKey: keys.inbox });
    qc.invalidateQueries({ queryKey: keys.approvals });
    qc.invalidateQueries({ queryKey: keys.notifications });
    qc.invalidateQueries({ queryKey: ["conversation"] });
  };
}

export function useApprove() {
  const invalidate = useInvalidateTripData();
  return useMutation({
    mutationFn: (a: Action) => api.post<Action>(`/approvals/${a.id}/approve`, { payload_hash: a.payload_hash }),
    onSettled: invalidate,
  });
}

export function useReject() {
  const invalidate = useInvalidateTripData();
  return useMutation({
    mutationFn: (a: Action) => api.post<Action>(`/approvals/${a.id}/reject`, {}),
    onSettled: invalidate,
  });
}

export { PROCESSING };
