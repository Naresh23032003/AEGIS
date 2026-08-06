import { describe, expect, it } from "vitest";

import { canonicalJson } from "./canonicalJson";

describe("canonicalJson", () => {
  it("sorts keys and strips whitespace, matching aegis.chain.canonical_json", () => {
    expect(
      canonicalJson({ decision: "approve", action_id: "act_1", ts: "2026-08-06T10:00:00.000Z" }),
    ).toBe('{"action_id":"act_1","decision":"approve","ts":"2026-08-06T10:00:00.000Z"}');
  });

  it("is stable regardless of input key order", () => {
    const a = canonicalJson({ z: 1, a: 2, m: 3 });
    const b = canonicalJson({ a: 2, m: 3, z: 1 });
    expect(a).toBe(b);
    expect(a).toBe('{"a":2,"m":3,"z":1}');
  });

  it("sorts nested object keys too", () => {
    expect(canonicalJson({ outer: { z: 1, a: 2 } })).toBe('{"outer":{"a":2,"z":1}}');
  });

  it("does not escape non-ASCII characters, matching ensure_ascii=False", () => {
    expect(canonicalJson({ label: "café" })).toBe('{"label":"café"}');
  });
});
