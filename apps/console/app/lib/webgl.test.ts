import { afterEach, describe, expect, it, vi } from "vitest";

import { hasWebGL } from "./webgl";

describe("hasWebGL", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("is false in jsdom, which implements no WebGL context", () => {
    // No mocking: this pins the real behavior of the test environment,
    // the same one every other unit test in this app runs under.
    expect(hasWebGL()).toBe(false);
  });

  it("is true when getContext returns a context object", () => {
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(
      {} as unknown as RenderingContext,
    );
    expect(hasWebGL()).toBe(true);
  });

  it("is false, not throwing, when getContext itself throws", () => {
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockImplementation(() => {
      throw new Error("WebGL disabled by policy");
    });
    expect(() => hasWebGL()).not.toThrow();
    expect(hasWebGL()).toBe(false);
  });
});
