// The two confidences on an action card are different measurements and the
// card has to keep them apart. The case pinned here is the real one from
// the error_spike_target-gateway fixtures: diagnose submitted 0.0
// (apps/core/fixtures/error_spike_target-gateway/diagnose_1.json), the
// remediation plan submitted 0.8 (plan_remediation_1.json). Rendering one
// of them under a bare "confidence" showed 80% and hid the 0%.

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ActionCard } from "./ActionCard";
import type { ActionView } from "../lib/fold";

const errorSpikeGateway: ActionView = {
  action_id: "act_01TESTTESTTESTTESTTESTTEST",
  status: "proposed",
  catalog_key: "restart_service",
  params: { service: "target-gateway" },
  tier: "green",
  diagnosisConfidence: 0.0,
  confidence: 0.8,
  reasoning: "Restarting the target-gateway service may resolve the high error rate issue.",
};

describe("ActionCard confidences", () => {
  it("renders a 0.0 diagnosis and a 0.8 action as two distinct labelled values", () => {
    render(<ActionCard action={errorSpikeGateway} />);

    const diagnosis = screen.getByTestId("diagnosis-confidence");
    const action = screen.getByTestId("action-confidence");

    expect(diagnosis).toHaveTextContent("diagnosis 0%");
    expect(action).toHaveTextContent("action 80%");
    expect(diagnosis).not.toBe(action);
    // The old bare label is what made the two indistinguishable.
    expect(screen.queryByText(/^confidence /)).toBeNull();
  });

  it("shows a zero diagnosis instead of dropping it", () => {
    render(<ActionCard action={errorSpikeGateway} />);
    // `!= null`, not truthiness: 0.0 is an answer, not a missing value.
    expect(screen.getByTestId("diagnosis-confidence")).toBeInTheDocument();
  });

  it("styles a zero diagnosis like data, not like an error", () => {
    render(<ActionCard action={errorSpikeGateway} />);
    const row = screen.getByTestId("diagnosis-confidence").parentElement;
    expect(row).toHaveClass("font-mono-data");
    expect(row).toHaveStyle({ color: "var(--aegis-text-secondary)" });
  });

  it("renders the action alone when no diagnosis confidence rode along", () => {
    render(<ActionCard action={{ ...errorSpikeGateway, diagnosisConfidence: undefined }} />);

    expect(screen.getByTestId("action-confidence")).toHaveTextContent("action 80%");
    expect(screen.queryByTestId("diagnosis-confidence")).toBeNull();
  });

  it("keeps both at their own precision when neither is zero", () => {
    render(
      <ActionCard action={{ ...errorSpikeGateway, diagnosisConfidence: 0.45, confidence: 0.9 }} />,
    );

    expect(screen.getByTestId("diagnosis-confidence")).toHaveTextContent("diagnosis 45%");
    expect(screen.getByTestId("action-confidence")).toHaveTextContent("action 90%");
  });
});
