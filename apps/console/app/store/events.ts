// The one Zustand store. plan/05-frontend.md, Frontend data layer: "One
// WebSocket connection ... feeding a Zustand store; all components select
// from the store" and "Replay mode swaps the store's source from live WS
// to the fetched event array; components are unaware." Consumers call
// `useVisibleEvents()`, never `events` or `replayEvents` directly, so a
// component genuinely cannot tell which source it is reading.

"use client";

import { useMemo } from "react";
import { create } from "zustand";

import type { EventEnvelope } from "../lib/types";
import { EventSocket, type WsStatus } from "../lib/ws";

const MAX_LIVE_EVENTS = 4000;
const WS_URL = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8080/ws/events";

interface EventStoreState {
  status: WsStatus;
  events: EventEnvelope[];
  socket: EventSocket | null;
  mode: "live" | "replay";
  replayEvents: EventEnvelope[];
  replayIndex: number;
  connect: () => void;
  disconnect: () => void;
  enterReplay: (events: EventEnvelope[]) => void;
  exitReplay: () => void;
  setReplayIndex: (index: number) => void;
}

export const useEventStore = create<EventStoreState>((set, get) => ({
  status: "closed",
  events: [],
  socket: null,
  mode: "live",
  replayEvents: [],
  replayIndex: -1,

  connect: () => {
    if (get().socket) return;
    const socket = new EventSocket(WS_URL);
    socket.onStatus = (status) => set({ status });
    socket.onEvent = (envelope) =>
      set((s) => ({ events: [...s.events, envelope].slice(-MAX_LIVE_EVENTS) }));
    socket.connect();
    set({ socket, status: "connecting" });
  },

  disconnect: () => {
    get().socket?.close();
    set({ socket: null, status: "closed" });
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
