import { afterEach, describe, expect, it } from "vitest";

import { readViewParam } from "./viewParam";

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
