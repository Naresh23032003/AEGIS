// plan/05-frontend.md, Frontend data layer: "The approval drawer takes
// initial focus on mount and traps focus while open (role=alertdialog
// semantics)." The final verification pass reached the approve button only
// after 59 Tab presses, because the drawer set no initial focus and sat
// behind the entire incident feed in document order.

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ApprovalDrawer } from "./ApprovalDrawer";
import type { ActionView } from "../lib/fold";

const action: ActionView = {
  action_id: "act_01TESTTESTTESTTESTTESTTEST",
  status: "awaiting_approval",
  catalog_key: "restart_database",
  params: {},
  tier: "red",
  approvalReasoning: "synthetic test action",
};

function renderDrawer() {
  render(<ApprovalDrawer incidentId="inc_01TESTTESTTESTTESTTESTTEST" action={action} />);
  return {
    drawer: screen.getByTestId("approval-drawer"),
    approve: screen.getByRole("button", { name: /approve/i }),
    reject: screen.getByRole("button", { name: /reject/i }),
  };
}

describe("ApprovalDrawer focus", () => {
  it("takes focus on mount, on the dialog rather than on approve", () => {
    const { drawer, approve } = renderDrawer();
    expect(document.activeElement).toBe(drawer);
    expect(document.activeElement).not.toBe(approve);
  });

  it("wraps Tab from the last control back to the first", () => {
    const { drawer, approve, reject } = renderDrawer();
    reject.focus();
    fireEvent.keyDown(drawer, { key: "Tab" });
    expect(document.activeElement).toBe(approve);
  });

  it("wraps Shift+Tab off the dialog and off the first control to the last", () => {
    const { drawer, approve, reject } = renderDrawer();
    fireEvent.keyDown(drawer, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(reject);

    approve.focus();
    fireEvent.keyDown(drawer, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(reject);
  });

  it("leaves interior Tab moves alone", () => {
    const { drawer, approve } = renderDrawer();
    approve.focus();
    const event = fireEvent.keyDown(drawer, { key: "Tab" });
    // fireEvent returns false when preventDefault was called; the browser
    // owns the move from approve to reject, the trap must not intercept it.
    expect(event).toBe(true);
    expect(document.activeElement).toBe(approve);
  });

  it("restores focus to whatever was focused before it mounted", () => {
    const before = document.createElement("button");
    document.body.appendChild(before);
    before.focus();

    const { unmount } = render(
      <ApprovalDrawer incidentId="inc_01TESTTESTTESTTESTTESTTEST" action={action} />,
    );
    expect(document.activeElement).toBe(screen.getByTestId("approval-drawer"));

    unmount();
    expect(document.activeElement).toBe(before);
    before.remove();
  });
});
