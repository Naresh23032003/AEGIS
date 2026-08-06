import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { LoopRing } from "./LoopRing";

describe("LoopRing", () => {
  it("renders all four segments unlit with no phases complete", () => {
    render(<LoopRing litPhases={[]} currentPhase={null} />);
    for (const phase of ["observe", "plan", "act", "verify"]) {
      const segment = screen.getByTestId(`loop-ring-segment-${phase}`);
      expect(segment).toHaveAttribute("data-lit", "false");
      expect(segment).toHaveAttribute("data-current", "false");
    }
  });

  it("lights completed phases and marks the current one", () => {
    render(<LoopRing litPhases={["observe", "plan"]} currentPhase="plan" />);
    expect(screen.getByTestId("loop-ring-segment-observe")).toHaveAttribute("data-lit", "true");
    expect(screen.getByTestId("loop-ring-segment-plan")).toHaveAttribute("data-lit", "true");
    expect(screen.getByTestId("loop-ring-segment-plan")).toHaveAttribute("data-current", "true");
    expect(screen.getByTestId("loop-ring-segment-act")).toHaveAttribute("data-lit", "false");
    expect(screen.getByTestId("loop-ring-segment-verify")).toHaveAttribute("data-lit", "false");
  });

  it("accepts a Set as well as an array for litPhases", () => {
    render(<LoopRing litPhases={new Set(["verify"])} currentPhase={null} />);
    expect(screen.getByTestId("loop-ring-segment-verify")).toHaveAttribute("data-lit", "true");
  });

  it("lights every segment green on a resolved incident, no pulse", () => {
    render(<LoopRing litPhases={["observe"]} currentPhase="verify" status="resolved" />);
    for (const phase of ["observe", "plan", "act", "verify"]) {
      const segment = screen.getByTestId(`loop-ring-segment-${phase}`);
      expect(segment).toHaveAttribute("data-lit", "true");
      expect(segment).toHaveAttribute("data-current", "false");
      expect(segment).toHaveAttribute("stroke", "var(--aegis-success)");
    }
  });

  it("lights every segment critical on an escalated incident", () => {
    render(<LoopRing litPhases={[]} currentPhase={null} status="escalated" />);
    expect(screen.getByTestId("loop-ring-segment-observe")).toHaveAttribute(
      "stroke",
      "var(--aegis-critical)",
    );
  });

  it("applies the pulse class to the current segment when motion is allowed", () => {
    render(<LoopRing litPhases={["act"]} currentPhase="act" />);
    expect(screen.getByTestId("loop-ring-segment-act").getAttribute("class")).toContain(
      "aegis-loop-ring-pulse",
    );
  });

  it("never pulses a non-current segment", () => {
    render(<LoopRing litPhases={["observe", "act"]} currentPhase="act" />);
    expect(screen.getByTestId("loop-ring-segment-observe").getAttribute("class")).toBeNull();
  });

  it("suppresses the pulse animation under prefers-reduced-motion", () => {
    const original = window.matchMedia;
    window.matchMedia = ((query: string) => ({
      matches: true,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    })) as typeof window.matchMedia;

    render(<LoopRing litPhases={["act"]} currentPhase="act" />);
    expect(screen.getByTestId("loop-ring-segment-act").getAttribute("class")).toBeNull();

    window.matchMedia = original;
  });

  it("exposes a status summary via aria-label", () => {
    render(<LoopRing litPhases={["observe"]} currentPhase="observe" />);
    const svg = screen.getByTestId("loop-ring");
    expect(svg.getAttribute("aria-label")).toContain("Observe complete");
    expect(svg.getAttribute("aria-label")).toContain("Plan pending");
    expect(svg.getAttribute("aria-label")).toContain("currently observe");
  });
});
