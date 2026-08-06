import { describe, expect, it } from "vitest";

import { activeScenarios } from "./chaosState";
import type { EventEnvelope } from "./types";

function ev(type: string, scenario: string): EventEnvelope {
  return {
    id: `evt_${Math.random()}`,
    ts: "2026-08-06T10:00:00.000Z",
    type,
    incident_id: "chaos",
    actor: "system:detector",
    payload: { scenario },
  };
}

describe("activeScenarios", () => {
  it("is empty with no events", () => {
    expect(activeScenarios([])).toEqual(new Set());
  });

  it("adds a scenario on inject, removes it on clear", () => {
    expect(activeScenarios([ev("chaos.injected", "crash")])).toEqual(new Set(["crash"]));
    expect(activeScenarios([ev("chaos.injected", "crash"), ev("chaos.cleared", "crash")])).toEqual(
      new Set(),
    );
  });

  it("tracks multiple scenarios independently", () => {
    const events = [
      ev("chaos.injected", "crash"),
      ev("chaos.injected", "latency"),
      ev("chaos.cleared", "crash"),
    ];
    expect(activeScenarios(events)).toEqual(new Set(["latency"]));
  });

  it("ignores events not on the chaos chain", () => {
    const events = [{ ...ev("chaos.injected", "crash"), incident_id: "inc_1" }];
    expect(activeScenarios(events)).toEqual(new Set());
  });
});
