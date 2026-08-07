import { afterEach, describe, expect, it } from "vitest";

import { readViewParam, withViewParam } from "./viewParam";

function setSearch(search: string) {
  window.history.pushState({}, "", `/${search}`);
}

describe("readViewParam", () => {
  afterEach(() => {
    setSearch("");
  });

  it("is null with no ?view= in the URL", () => {
    expect(readViewParam()).toBeNull();
  });

  it("reads a valid ?view=2d or ?view=3d", () => {
    setSearch("?view=2d");
    expect(readViewParam()).toBe("2d");
    setSearch("?view=3d");
    expect(readViewParam()).toBe("3d");
  });

  it("is null for any other value, not the literal string", () => {
    setSearch("?view=bogus");
    expect(readViewParam()).toBeNull();
  });
});

describe("withViewParam", () => {
  afterEach(() => {
    setSearch("");
  });

  it("leaves the path alone when no override is set", () => {
    expect(withViewParam("/")).toBe("/");
    expect(withViewParam("/chaos")).toBe("/chaos");
  });

  it("carries an active override onto the next path", () => {
    setSearch("?view=2d");
    expect(withViewParam("/")).toBe("/?view=2d");
    expect(withViewParam("/chaos")).toBe("/chaos?view=2d");
    setSearch("?view=3d");
    expect(withViewParam("/")).toBe("/?view=3d");
  });

  it("does not carry a bogus value", () => {
    setSearch("?view=bogus");
    expect(withViewParam("/")).toBe("/");
  });
});
