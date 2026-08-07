"""prefers-reduced-motion, including the 3D scene a user can force back on.

plan/05-frontend.md, Fallback: reduced motion routes to the React Flow
renderer, and "if a reduced-motion user forces 3D with ?view=3d, the scene
mounts but renders static: no idle ticker, no ambient pulse, frames render
only on state changes."

Defect 6 in docs/reports/FINAL_VERIFICATION.md: Topology3D never called
useReducedMotion, so the forced scene breathed at 5fps exactly like the
unforced one. The control case below is what gives the assertion teeth,
since identical screenshots would otherwise also be what a scene that
failed to render at all produces.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from e2e.conftest import CONSOLE_URL, VIEWPORT

IDLE_GAP_SECONDS = 4
SETTLE_SECONDS = 3
CANVAS = "[data-testid=topology-3d] canvas"


def _canvas_across_an_idle_gap(browser: Any, *, reduced: bool) -> tuple[bytes, bytes]:
    context = browser.new_context(
        viewport=VIEWPORT, reduced_motion="reduce" if reduced else "no-preference"
    )
    page = context.new_page()
    try:
        page.goto(f"{CONSOLE_URL}/?view=3d", wait_until="domcontentloaded")
        page.wait_for_selector(CANVAS, timeout=30_000)
        assert page.locator("[data-testid=topology-2d]").count() == 0
        time.sleep(SETTLE_SECONDS)  # let the camera settle at its resting pose
        first = page.locator(CANVAS).screenshot()
        time.sleep(IDLE_GAP_SECONDS)
        return first, page.locator(CANVAS).screenshot()
    finally:
        context.close()


def _assert_default_renderer_is_2d(browser: Any) -> None:
    """The path a reduced-motion user gets without asking for 3D. Passing
    already in the final verification; asserted here so the ?view=3d case
    below cannot be read as the only reduced-motion behaviour that matters."""
    context = browser.new_context(viewport=VIEWPORT, reduced_motion="reduce")
    page = context.new_page()
    try:
        page.goto(CONSOLE_URL, wait_until="domcontentloaded")
        page.wait_for_selector("[data-testid=topology-2d]", timeout=30_000)
        assert page.locator("[data-testid=topology-3d]").count() == 0
        running = "document.getAnimations().filter(a => a.playState === 'running')"
        assert page.evaluate(running) == []
    finally:
        context.close()


def test_forced_3d_holds_still_under_reduced_motion(client: httpx.Client, browser: Any) -> None:
    for scenario in ("latency", "crash", "error_spike", "memory_leak", "cache_outage"):
        client.delete(f"/api/chaos/{scenario}")

    _assert_default_renderer_is_2d(browser)

    still_first, still_second = _canvas_across_an_idle_gap(browser, reduced=True)
    assert still_first == still_second, (
        f"forced 3D scene animated under reduced motion "
        f"({len(still_first)} vs {len(still_second)} bytes)"
    )

    # Control: the same scene, same idle gap, no preference set. If this
    # one also came back identical the check above would be measuring a
    # dead canvas rather than a respected preference.
    moving_first, moving_second = _canvas_across_an_idle_gap(browser, reduced=False)
    assert moving_first != moving_second, "the 3D scene never moved even without reduced motion"
