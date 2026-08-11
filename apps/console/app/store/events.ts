// The one Zustand store. plan/05-frontend.md, Frontend data layer: "One
// WebSocket connection ... feeding a Zustand store; all components select
// from the store" and "Replay mode swaps the store's source from live WS
// to the fetched event array; components are unaware." Consumers call
// `useVisibleEvents()`, never `events` or `replayEvents` directly, so a
// component genuinely cannot tell which source it is reading.
//
// Seeding, also plan/05: "On connect (and reconnect) the store seeds
// itself from REST before live-tailing: open incidents, plus the full
// event log for any incident in awaiting_approval." /ws/events tails Redis
// from `$` with no backfill, so without this the store starts empty on
// every page load and an approval parked a minute ago has no events to
// fold: defect 5 in docs/reports/FINAL_VERIFICATION.md, a red-tier action
// that became unapprovable from the UI after a refresh. The fetch lives
// here rather than in ApprovalOverlays because components still select and
// never fetch live data themselves.

"use client";

import { useMemo } from "react";
import { create } from "zustand";

import { getIncidentEvents, listIncidents } from "../lib/api";
import type { EventEnvelope } from "../lib/types";
import { EventSocket, type WsStatus } from "../lib/ws";

const MAX_LIVE_EVENTS = 4000;
const SEED_INCIDENT_LIMIT = 50;
const WS_URL = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8080/ws/events";

/** An incident is "open" until it reaches one of the two terminal states.
 * Statuses are the incident.schema.json enum. */
const OPEN_STATUSES = new Set(["open", "resolving", "awaiting_approval"]);

interface EventStoreState {
  status: WsStatus;
  events: EventEnvelope[];
  socket: EventSocket | null;
  seeded: boolean;
  mode: "live" | "replay";
  replayEvents: EventEnvelope[];
  replayIndex: number;
  connect: () => void;
  disconnect: () => void;
  seed: () => Promise<void>;
  mergeSeed: (seeded: EventEnvelope[]) => void;
  enterReplay: (events: EventEnvelope[]) => void;
  exitReplay: () => void;
  setReplayIndex: (index: number) => void;
}

export const useEventStore = create<EventStoreState>((set, get) => ({
  status: "closed",
  events: [],
  socket: null,
  seeded: false,
  mode: "live",
  replayEvents: [],
  replayIndex: -1,

  connect: () => {
    if (get().socket) return;
    const socket = new EventSocket(WS_URL);
    socket.onStatus = (status) => {
      set({ status });
      // Fires on the first connect and on every reconnect, which is
      // exactly when the store may have missed events it can no longer
      // receive from a `$`-anchored tail.
      if (status === "open") void get().seed();
    };
    socket.onEvent = (envelope) =>
      set((s) =>
        s.events.some((e) => e.id === envelope.id)
          ? {}
          : { events: [...s.events, envelope].slice(-MAX_LIVE_EVENTS) },
      );
    socket.connect();
    set({ socket, status: "connecting" });
  },

  /** Reads the event log of every incident that has not finished yet. The
   * awaiting_approval ones are the reason this exists; the other open
   * states come along because the same query answers both and an incident
   * mid-run is just as invisible after a reload otherwise. */
  seed: async () => {
    try {
      const incidents = await listIncidents({ limit: SEED_INCIDENT_LIMIT });
      const open = incidents.filter((i) => OPEN_STATUSES.has(i.status));
      const logs = await Promise.all(
        open.map((i) => getIncidentEvents(i.id).catch(() => [] as EventEnvelope[])),
      );
      get().mergeSeed(logs.flat());
    } catch {
      // A failed seed is not fatal: the live tail still runs, and the
      // incident feed keeps its own REST seed. Nothing to surface beyond
      // the connection badge.
    } finally {
      set({ seeded: true });
    }
  },

  /** Idempotent against the live tail. Anything the socket already
   * delivered while the REST call was in flight is dropped by id, and the
   * rest goes in front of the live events so each incident's own slice
   * stays in seq order (foldAllIncidents groups by incident, so ordering
   * between incidents does not matter). */
  mergeSeed: (seeded) =>
    set((s) => {
      const known = new Set(s.events.map((e) => e.id));
      const fresh = seeded.filter((e) => !known.has(e.id));
      return fresh.length === 0 ? {} : { events: [...fresh, ...s.events].slice(-MAX_LIVE_EVENTS) };
    }),

  disconnect: () => {
    get().socket?.close();
    set({ socket: null, status: "closed", seeded: false });
  },

  enterReplay: (events) =>
    set({ mode: "replay", replayEvents: events, replayIndex: events.length - 1 }),

  exitReplay: () => set({ mode: "live", replayEvents: [], replayIndex: -1 }),

  setReplayIndex: (index) =>
    set((s) => ({ replayIndex: Math.max(0, Math.min(index, s.replayEvents.length - 1)) })),
}));

/** The single source components read from, whichever mode is active.
 * Selects the four raw fields (each a stable reference from Zustand
 * unless actually replaced by set()) and only computes the replay slice
 * in a useMemo -- slicing directly inside the Zustand selector would
 * return a new array on every call, which breaks useSyncExternalStore's
 * snapshot-caching contract and free-spins into React error #185 (found
 * live navigating to the flight recorder page, see
 * docs/reports/PHASE_4_REPORT.md, Deviations). */
export function useVisibleEvents(): EventEnvelope[] {
  const mode = useEventStore((s) => s.mode);
  const liveEvents = useEventStore((s) => s.events);
  const replayEvents = useEventStore((s) => s.replayEvents);
  const replayIndex = useEventStore((s) => s.replayIndex);
  return useMemo(
    () => (mode === "replay" ? replayEvents.slice(0, replayIndex + 1) : liveEvents),
    [mode, liveEvents, replayEvents, replayIndex],
  );
}

export function useConnectionStatus(): WsStatus {
  return useEventStore((s) => s.status);
}
