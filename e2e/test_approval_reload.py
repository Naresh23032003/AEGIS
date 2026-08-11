"""A parked red-tier approval must still be approvable from the UI after a
page reload. plan/05-frontend.md, Frontend data layer: "On connect (and
reconnect) the store seeds itself from REST before live-tailing: open
incidents, plus the full event log for any incident in awaiting_approval."

Defect 5 in docs/reports/FINAL_VERIFICATION.md, the most serious thing that
pass found. ApprovalOverlays folded live WebSocket events only, and
/ws/events tails Redis from `$` with no backfill, so the drawer rendered
only for a park that happened while the page was already open. Refresh the
tab and the approve and reject buttons were gone: no other screen carries
an approval control, so the operator's only remaining route was POST
/api/approvals by hand. This test reloads mid-park and approves from the
drawer that the seed brings back.
"""

from __future__ import annotations

from typing import Any

import httpx

from e2e.conftest import CONSOLE_URL, VIEWPORT, events_for, verify_chain, wait_for_resolution
from e2e.test_approvals import _seed_parked_red_action

DRAWER = "[data-testid=approval-drawer]"


def test_a_parked_approval_survives_a_page_reload(client: httpx.Client, browser: Any) -> None:
    context = browser.new_context(viewport=VIEWPORT)
    page = context.new_page()
    try:
        page.goto(CONSOLE_URL, wait_until="domcontentloaded")
        page.wait_for_selector("[data-testid=metrics-strip]", timeout=30_000)

        incident_id, action_id = _seed_parked_red_action()
        # Scoped to this action id: a drawer left over from another test's
        # park would otherwise satisfy the wait and the approval below
        # would go to the wrong action.
        parked = f'{DRAWER}:has-text("{action_id}")'
        page.wait_for_selector(parked, timeout=30_000)

        # The park is now history as far as the socket is concerned: a
        # reload reconnects the tail at `$` and the drawer can only come
        # back from the REST seed.
        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector(parked, timeout=30_000)
        assert page.get_attribute(DRAWER, "role") == "alertdialog"

        page.click(f"{parked} >> text=approve")
        # The drawer's own "approved, signed <fingerprint>" line is on
        # screen only between the POST returning and the resolution event
        # arriving, about a second in fixture mode, so the stable signal is
        # the drawer going away. What was actually signed is checked
        # against the event log below.
        page.wait_for_selector(DRAWER, state="detached", timeout=60_000)
    finally:
        context.close()

    resolved = wait_for_resolution(client, incident_id)
    assert resolved["status"] == "resolved", resolved
    assert resolved["autonomy"] == "approved", resolved

    events = events_for(client, incident_id)
    approved = [e for e in events if e["type"] == "action.approved"]
    assert approved, events
    assert approved[0]["actor"].startswith("human:"), approved[0]
    assert approved[0]["payload"]["action_id"] == action_id, approved[0]
    assert any(e["type"] == "action.executed" for e in events), events

    chain = verify_chain(client, incident_id)
    assert chain["valid"], chain
