// plan/05-frontend.md, Frontend data layer: the store seeds from REST on
// connect and reconnect, then live-tails. The seed and the tail overlap by
// construction (the REST read and the socket race), so the merge has to be
// idempotent: defect 5's gotcha in plan/phases/phase-7.md, "events arriving
// twice must fold identically. Dedupe by event id in the store."

import { beforeEach, describe, expect, it, vi } from "vitest";

import type { EventEnvelope } from "../lib/types";
import { foldAllIncidents } from "../lib/fold";

vi.mock("../lib/api", () => ({
  listIncidents: vi.fn(),
  getIncidentEvents: vi.fn(),
}));

const { getIncidentEvents, listIncidents } = await import("../lib/api");
const { useEventStore } = await import("./events");

const INCIDENT = "inc_01SEEDSEEDSEEDSEEDSEEDSEED";
const ACTION = "act_01SEEDSEEDSEEDSEEDSEEDSEED";

function event(id: string, type: string, payload: Record<string, unknown> = {}): EventEnvelope {
  return {
    id,
    ts: "2026-08-07T05:00:00.000Z",
    type,
    incident_id: INCIDENT,
    actor: "system:supervisor",
    payload,
  };
}

const DETECTED = event("evt_1", "incident.detected", {
  rule: "synthetic",
  service: "target-payments",
});
const CHECKED = event("evt_2", "action.policy_checked", { action_id: ACTION, decision: "allow" });
const REQUESTED = event("evt_3", "action.approval_requested", {
  action_id: ACTION,
  diff: { catalog_key: "restart_database", params: {} },
  reasoning: "synthetic",
});
const PARKED: EventEnvelope[] = [DETECTED, CHECKED, REQUESTED];

beforeEach(() => {
  useEventStore.setState({ events: [], seeded: false, mode: "live", replayEvents: [] });
  vi.mocked(listIncidents).mockReset();
  vi.mocked(getIncidentEvents).mockReset();
});

describe("event store seeding", () => {
  it("pulls the full event log of an awaiting_approval incident", async () => {
    vi.mocked(listIncidents).mockResolvedValue([
      { id: INCIDENT, status: "awaiting_approval" } as never,
    ]);
    vi.mocked(getIncidentEvents).mockResolvedValue(PARKED);

    await useEventStore.getState().seed();

    const events = useEventStore.getState().events;
    expect(events.map((e) => e.id)).toEqual(["evt_1", "evt_2", "evt_3"]);
    expect(useEventStore.getState().seeded).toBe(true);

    const view = foldAllIncidents({}, events)[INCIDENT];
    expect(view?.actions[ACTION]?.status).toBe("awaiting_approval");
  });

  it("skips incidents that already reached a terminal state", async () => {
    vi.mocked(listIncidents).mockResolvedValue([
      { id: "inc_resolved", status: "resolved" } as never,
      { id: "inc_escalated", status: "escalated" } as never,
    ]);

    await useEventStore.getState().seed();

    expect(getIncidentEvents).not.toHaveBeenCalled();
    expect(useEventStore.getState().events).toEqual([]);
  });

  it("folds identically whether an event arrived live, seeded, or both", async () => {
    // evt_1 and evt_2 arrived on the socket while the REST read was in
    // flight; the seed returns all three.
    useEventStore.setState({ events: [DETECTED, CHECKED] });
    vi.mocked(listIncidents).mockResolvedValue([
      { id: INCIDENT, status: "awaiting_approval" } as never,
    ]);
    vi.mocked(getIncidentEvents).mockResolvedValue(PARKED);

    await useEventStore.getState().seed();
    const once = useEventStore.getState().events;
    expect(once.map((e) => e.id).sort()).toEqual(["evt_1", "evt_2", "evt_3"]);

    // Reconnect: the same seed lands again and must change nothing.
    await useEventStore.getState().seed();
    const twice = useEventStore.getState().events;
    expect(twice).toBe(once);
    expect(foldAllIncidents({}, twice)).toEqual(foldAllIncidents({}, PARKED));
  });

  it("keeps each incident's events in seq order ahead of the live tail", () => {
    const later = event("evt_9", "action.approved", { action_id: ACTION });
    useEventStore.setState({ events: [later] });

    useEventStore.getState().mergeSeed(PARKED);

    expect(useEventStore.getState().events.map((e) => e.id)).toEqual([
      "evt_1",
      "evt_2",
      "evt_3",
      "evt_9",
    ]);
  });

  it("survives a failed REST read without wiping the live tail", async () => {
    useEventStore.setState({ events: [DETECTED] });
    vi.mocked(listIncidents).mockRejectedValue(new Error("API unreachable"));

    await useEventStore.getState().seed();

    expect(useEventStore.getState().events).toEqual([DETECTED]);
    expect(useEventStore.getState().seeded).toBe(true);
  });
});
