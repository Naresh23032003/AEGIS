#!/usr/bin/env python3
"""python scripts/record_demo.py [--output-dir docs/media]

Records the README/LinkedIn demo against an already-running stack
(`MOCK_LLM=1 make up` first, then `make demo`). One continuous browser
session, two acts, captions burned into the page so they narrate events
that actually happened rather than a timer:

  act one, crash    inject -> detect -> read evidence -> green tier -> healed
  act two, latency  inject -> restart_service -> closed with the toxic still on

Act two is the point of the recording. The model proposes restart_service
for a Toxiproxy toxic, the restart does nothing to it, and the incident
closes anyway because verification never compares p95 against its
threshold (rules.yaml keys the query `p95_latency`, the rule's id is
`latency_p95`, so tools.py's threshold lookup misses). The run ends on the
name of the CI test that fails because of it, not on a heal.

Two artifacts come out of the single capture:

  docs/media/demo.gif   880x550, the size the README already uses
  docs/media/demo.mp4   1080x1080 h264, no audio track, for a muted feed

Nothing here fixes, hides, or works around the verification bug. The
recording exists to show it.

MOCK_LLM=1 is required, and checked: the fixture responses are what make
the two acts reproduce the same way every time, and they need no API key.

The stack-quiet helpers are imported from e2e/conftest.py rather than
reimplemented. "Is this stack quiet enough to inject into" is subtle
(plan/03's one-incident-per-firing-episode rule means a fault injected
inside a still-hot rate() window is deduped into the previous incident and
never gets one of its own), and a second copy of that reasoning would be a
second place for it to be wrong.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import httpx  # noqa: E402

from e2e.conftest import (  # noqa: E402
    API_URL,
    COMPOSE,
    CONSOLE_URL,
    wait_for_incident,
    wait_for_no_open_incidents,
    wait_for_resolution,
    wait_for_rules_quiet,
)

SCENARIOS = ("latency", "crash", "error_spike", "memory_leak", "cache_outage")

# 16:10, the aspect the README GIF already has, and wide enough for the
# console's three-column layout (feed 320 + topology + detail 400).
CAPTURE_SIZE = {"width": 1600, "height": 1000}
GIF_WIDTH = 880  # -> 880x550, unchanged from the GIF the README links now
# 6fps and a flat 64-colour palette. Two acts run about three times as long
# as the single-act GIF this replaces, and the defaults that suited 36
# seconds produced a 20MB file: measured 10.1MB at 8fps/96 dithered, 6.3MB
# here, against 5.3MB for the old one-act GIF. Dithering a dark flat UI
# bought nothing but noise for the encoder to carry.
GIF_FPS = 6
GIF_COLORS = 64
SQUARE = 1080  # LinkedIn's square slot
PAGE_BG = "0x050607"  # --aegis-bg, so the square's letterbox is not a grey bar

# A caption a viewer cannot finish reading is a caption that was not
# there. Feed video autoplays muted and scrolls past, so every card gets
# at least this long on screen even when the event it describes resolved
# faster than that.
MIN_CAPTION_SECONDS = 2.5
SETTLE_SECONDS = 1.0
PAINT_TIMEOUT_MS = 60_000

# Injected once per document. Survives a full reload by keeping the current
# caption in sessionStorage, which matters because act two reloads the
# console to pick up the verify marker. Appended outside the React root and
# never animated: no transition to suppress under prefers-reduced-motion,
# and nothing for React to reconcile.
CAPTION_SCRIPT = """
(() => {
  const ID = "aegis-demo-caption";
  const KEY = "aegis-demo-caption";
  const MONO = "var(--font-mono), ui-monospace, SFMono-Regular, Menlo, monospace";

  function render() {
    const raw = window.sessionStorage.getItem(KEY);
    let el = document.getElementById(ID);
    if (!raw) {
      if (el) el.remove();
      return;
    }
    const { title, subtitle } = JSON.parse(raw);
    if (!el) {
      el = document.createElement("div");
      el.id = ID;
      // Glass over surface-raised is the design system's overlay treatment
      // (design-system/MASTER.md, Style). The caption needs it: it sits over
      // the incident feed on the left and the metrics strip along the
      // bottom, and unbacked text was unreadable against both. bottom
      // clears the strip rather than landing on it.
      el.style.cssText = [
        "position:fixed",
        "left:32px",
        "bottom:56px",
        "z-index:2147483647",
        "pointer-events:none",
        "padding:12px 18px 13px 15px",
        "border-radius:6px",
        "border-left:3px solid var(--aegis-success, #34D399)",
        "background:rgba(18, 22, 27, 0.82)",
        "backdrop-filter:blur(12px)",
        "-webkit-backdrop-filter:blur(12px)",
        "font-family:" + MONO,
      ].join(";");
      document.body.appendChild(el);
    }
    el.innerHTML = "";
    const h = document.createElement("div");
    h.style.cssText =
      "font-size:26px;line-height:1.25;color:var(--aegis-text, #E6EDF3)";
    h.textContent = title;
    el.appendChild(h);
    if (subtitle) {
      const s = document.createElement("div");
      s.style.cssText =
        "font-size:18px;line-height:1.35;margin-top:6px;color:var(--aegis-text-secondary, #8B98A5)";
      s.textContent = subtitle;
      el.appendChild(s);
    }
  }

  window.__aegisCaption = (title, subtitle) => {
    window.sessionStorage.setItem(KEY, JSON.stringify({ title, subtitle }));
    render();
  };
  window.__aegisCaptionClear = () => {
    window.sessionStorage.removeItem(KEY);
    render();
  };

  if (document.readyState === "complete") render();
  else window.addEventListener("load", render);
})();
"""


class Preflight(Exception):
    """Something about the stack means the recording would not be the one
    this script claims to make."""


def _run(argv: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
    """Fixed argv, never a shell string (CLAUDE.md: no shell=True anywhere)."""
    return subprocess.run(argv, capture_output=True, text=True, check=False, **kw)  # noqa: S603


def check_mock_llm() -> None:
    """MOCK_LLM lives in the worker's environment, not this process's, so
    ask the container that will actually answer the prompts."""
    proc = _run([*COMPOSE, "exec", "-T", "core-worker", "printenv", "MOCK_LLM"], timeout=30)
    value = proc.stdout.strip()
    if value != "1":
        raise Preflight(
            f"core-worker has MOCK_LLM={value or '(unset)'}; this recording is only "
            "reproducible on fixtures. Set MOCK_LLM=1 in .env and re-run `make up`."
        )


def check_reachable(client: httpx.Client) -> None:
    try:
        client.get("/healthz").raise_for_status()
    except httpx.HTTPError as exc:
        raise Preflight(
            f"core-api not reachable at {API_URL} ({exc}). Run `make up` first."
        ) from exc
    try:
        httpx.get(CONSOLE_URL, timeout=10.0).raise_for_status()
    except httpx.HTTPError as exc:
        raise Preflight(f"console not reachable at {CONSOLE_URL} ({exc}).") from exc


def check_ffmpeg() -> str:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise Preflight("ffmpeg not found on PATH; both artifacts are encoded with it.")
    return ffmpeg


def quiesce(client: httpx.Client) -> None:
    """Clear every fault and wait for the stack to look untouched, so the
    opening frame is honest and act one's injection opens its own incident."""
    for scenario in SCENARIOS:
        client.delete(f"/api/chaos/{scenario}")
    still_open = wait_for_no_open_incidents(client)
    if still_open:
        raise Preflight(f"incidents still running, nothing to record over: {still_open}")
    hot = wait_for_rules_quiet()
    if hot:
        raise Preflight(
            f"detection rules still over threshold: {hot}. A fault injected now would be "
            "deduped into the previous firing episode instead of opening its own incident."
        )


class Take:
    """The page under capture, plus the two clocks that matter: how long the
    current caption has been up, and how far into the video the first
    painted frame landed."""

    def __init__(self, page: Any, started_at: float) -> None:
        self.page = page
        self.started_at = started_at
        self.paint_offset = 0.0
        self._caption_at = 0.0

    def caption(self, title: str, subtitle: str | None = None) -> None:
        self.page.evaluate("([t, s]) => window.__aegisCaption(t, s)", [title, subtitle])
        self._caption_at = time.monotonic()
        print(f"  caption: {title}" + (f" / {subtitle}" if subtitle else ""))

    def hold(self, seconds: float = MIN_CAPTION_SECONDS) -> None:
        time.sleep(seconds)

    def hold_out(self, extra: float = 0.0) -> None:
        """Sleep until the current caption has had its minimum read time,
        plus `extra` for a frame worth dwelling on."""
        elapsed = time.monotonic() - self._caption_at
        time.sleep(max(0.0, MIN_CAPTION_SECONDS - elapsed) + extra)

    def wait_painted(self) -> None:
        """The first frame the recording is allowed to open on: topology
        drawn, socket live, feed done with its skeleton."""
        page = self.page
        page.wait_for_selector(
            "[data-testid=topology-3d] canvas, [data-testid=topology-2d]",
            timeout=PAINT_TIMEOUT_MS,
        )
        page.wait_for_function(
            "() => { const b = document.querySelector('[role=status]');"
            " return b && b.textContent.trim() === 'live'; }",
            timeout=PAINT_TIMEOUT_MS,
        )
        page.wait_for_function(
            "() => !document.querySelector('[aria-busy=true]')",
            timeout=PAINT_TIMEOUT_MS,
        )
        self._nudge_scene()
        time.sleep(SETTLE_SECONDS)

    def _nudge_scene(self) -> None:
        """A mounted canvas is not a composited canvas.

        Under reduced motion the scene runs frameloop="demand" with the idle
        ticker off (Topology3D.tsx). During a run that is fine, because
        incidents keep changing state and every change invalidates and
        repaints. Straight after a reload nothing changes for several
        seconds, and the screencast the video is built from carried a black
        layer for that whole stretch: three seconds of empty topology in the
        middle of act two, in the first take.

        A resize event is the cheapest invalidate that alters nothing on
        screen, since the viewport is not actually changing. It re-renders
        the same still frame and the layer goes back in the capture.

        There is nothing to assert against afterwards: an element screenshot
        forces its own readback, so Playwright reports a drawn canvas even in
        the frames the video shows black. The nudge is verified by watching
        the encoded output, not from in here.
        """
        if self.page.locator("[data-testid=topology-3d] canvas").count() == 0:
            return  # 2D renderer, plain DOM, nothing on demand
        for _ in range(2):
            self.page.evaluate("() => window.dispatchEvent(new Event('resize'))")
            self.page.wait_for_timeout(350)

    def wait_for_panel_text(self, *needles: str, timeout: float = 180.0) -> None:
        """Poll the detail panel until every needle is on screen. Reading the
        rendered panel, not the API, so the caption only goes up once the
        thing it describes is actually visible in frame."""
        deadline = time.monotonic() + timeout
        panel = self.page.locator("[data-testid=detail-panel]")
        while True:
            text = panel.inner_text() if panel.count() else ""
            missing = [n for n in needles if n not in text]
            if not missing:
                return
            if time.monotonic() >= deadline:
                raise TimeoutError(f"detail panel never showed {missing} within {timeout}s")
            self.page.wait_for_timeout(500)

    def goto_nav(self, label: str) -> None:
        """Client-side navigation via the nav bar, so the overlay and the
        WebSocket store both survive the move."""
        self.page.get_by_role("link", name=label, exact=True).click()

    def select_incident(self, incident_id: str) -> None:
        """Click the card, which pins the detail panel to this incident.

        The console otherwise auto-follows the newest incident, and act two
        leaves a fault installed on purpose: slow orders push errors through
        the gateway, error_rate fires there, and a second incident arrives
        and steals the panel mid-caption. Pinning keeps the frame on the
        incident the caption is talking about. The cascade is real and stays
        visible in the feed.
        """
        card = f"[data-incident-id='{incident_id}']"
        self.page.wait_for_selector(card, timeout=PAINT_TIMEOUT_MS)
        self.page.click(card)


def act_one_crash(take: Take, client: httpx.Client) -> None:
    """Healthy topology, inject, detection, evidence, green tier, healed."""
    print("act one: crash")
    take.caption("The system, healthy", "Three services, a database, a shared cache")
    take.hold_out(extra=1.0)

    take.goto_nav("chaos")
    take.page.wait_for_selector("[data-testid=inject-crash]", timeout=30_000)
    take.caption(
        "Break something on purpose",
        "The operator panel names the fix. The prompt no longer does.",
    )
    take.hold_out(extra=1.5)

    injected_at = time.time()
    take.page.click("[data-testid=inject-crash]")

    take.caption("Detected", "A rule fires after 3 consecutive failed probes")
    incident = wait_for_incident(
        client, source_rule="service_down", service="target-payments", after=injected_at
    )
    take.select_incident(incident["id"])
    take.hold_out(extra=1.5)

    take.caption("It reads the evidence first", "query_metrics, query_logs, get_container_stats")
    take.wait_for_panel_text("query_metrics()", "query_logs()", "get_container_stats()")
    take.hold_out(extra=1.5)

    # The policy gate's verdict lands on the action card (opa rule id and
    # the green tier chip), so let it render before claiming the heal.
    take.wait_for_panel_text("restart_service", "green")
    resolved = wait_for_resolution(client, incident["id"])
    mttr = resolved["mttr_seconds"]
    # Caption copy carries the number this run actually produced. CLAUDE.md,
    # writing rules: every number in launch copy comes from an actual run.
    take.caption(f"Healed in {mttr}s", "Every step above is hash-chained and replayable")
    take.hold_out(extra=2.0)
    print(f"  crash resolved in {mttr}s, autonomy={resolved['autonomy']}")


def act_two_latency(take: Take, client: httpx.Client) -> str:
    """The one that does not work. Returns the incident id."""
    print("act two: latency")
    take.goto_nav("chaos")
    take.page.wait_for_selector("[data-testid=inject-latency]", timeout=30_000)
    take.caption("Now the one that does not work", "1500ms of injected latency on orders")
    take.hold_out(extra=1.5)

    injected_at = time.time()
    take.page.click("[data-testid=inject-latency]")

    incident = wait_for_incident(
        client, source_rule="latency_p95", service="target-orders", after=injected_at
    )
    take.select_incident(incident["id"])

    take.caption("It restarted a service that was never down", "The toxic is still installed")
    take.wait_for_panel_text("restart_service", "target-orders")
    take.hold_out(extra=2.0)

    resolved = wait_for_resolution(client, incident["id"])
    print(f"  latency closed in {resolved['mttr_seconds']}s, status={resolved['status']}")

    fault = client.get("/api/chaos/latency").json()["fault_present"]
    if fault is not True:
        raise Preflight(
            f"latency closed with fault_present={fault}; act two only exists because the "
            "toxic survives verification. Nothing to record."
        )

    # The marker is appended to incidents.summary by the verify node, after
    # incident.classified already put the unmarked summary on the wire. The
    # live fold replays that event over the REST seed, so the marker only
    # shows on a page that seeds fresh: reload, which is also exactly what
    # an operator opening the console later would see.
    take.page.reload(wait_until="domcontentloaded")
    take.wait_painted()
    take.select_incident(incident["id"])
    take.caption("Closed, and it says so", "injected fault still present at verify")
    take.wait_for_panel_text("[injected fault still present at verify]")
    take.hold_out(extra=2.5)

    # Ends on the failing test, not on a green frame.
    take.caption("test_latency_heals fails in CI on purpose")
    take.hold(MIN_CAPTION_SECONDS + 1.5)
    return str(incident["id"])


def capture(client: httpx.Client, video_dir: Path, reduced_motion: str) -> tuple[Path, float]:
    """Drive both acts in one browser session. Returns the raw video and how
    far into it the first fully painted frame sits."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(
            viewport=CAPTURE_SIZE,
            record_video_dir=str(video_dir),
            record_video_size=CAPTURE_SIZE,
            reduced_motion=reduced_motion,
        )
        context.add_init_script(CAPTION_SCRIPT)
        page = context.new_page()
        take = Take(page, time.monotonic())
        # ?view=3d under "reduce" is the forced-3D path: the scene mounts and
        # renders on state changes only, no idle ticker or ambient pulse
        # (plan/05-frontend.md, Fallback). withViewParam carries the
        # parameter across in-app navigation, so both acts keep the same
        # renderer.
        url = f"{CONSOLE_URL}/?view=3d" if reduced_motion == "reduce" else CONSOLE_URL
        try:
            page.goto(url, wait_until="domcontentloaded")
            take.wait_painted()
            # Everything before this instant is navigation and skeleton, and
            # gets trimmed off the front of both artifacts.
            take.paint_offset = time.monotonic() - take.started_at
            act_one_crash(take, client)
            act_two_latency(take, client)
        finally:
            video = page.video
            context.close()
            browser.close()
        if video is None:
            raise Preflight("playwright recorded no video")
        return Path(video.path()), take.paint_offset


def encode_gif(ffmpeg: str, source: Path, offset: float, out: Path) -> None:
    """Two-pass palette in one graph: build it from the pixels that move,
    then map with no dithering, which is what keeps two minutes of dark flat
    UI down to a file a README can carry."""
    vf = (
        f"fps={GIF_FPS},scale={GIF_WIDTH}:-1:flags=lanczos,"
        f"split[a][b];[a]palettegen=max_colors={GIF_COLORS}:stats_mode=diff[p];"
        "[b][p]paletteuse=dither=none:diff_mode=rectangle"
    )
    proc = _run(
        [ffmpeg, "-y", "-ss", f"{offset:.3f}", "-i", str(source), "-vf", vf, "-loop", "0", str(out)]
    )
    if proc.returncode != 0:
        raise Preflight(f"gif encode failed:\n{proc.stderr[-2000:]}")


def encode_mp4(ffmpeg: str, source: Path, offset: float, out: Path) -> None:
    """Square, letterboxed on the page background rather than cropped: the
    console's three columns are the content, and cropping to 1:1 would cut
    the detail panel the last two captions point at."""
    vf = (
        f"scale={SQUARE}:-2:flags=lanczos,"
        f"pad={SQUARE}:{SQUARE}:(ow-iw)/2:(oh-ih)/2:color={PAGE_BG}"
    )
    proc = _run(
        [
            ffmpeg, "-y", "-ss", f"{offset:.3f}", "-i", str(source),
            "-vf", vf,
            "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p",
            "-crf", "20", "-preset", "slow", "-movflags", "+faststart",
            "-an", str(out),
        ]
    )
    if proc.returncode != 0:
        raise Preflight(f"mp4 encode failed:\n{proc.stderr[-2000:]}")


def probe(ffmpeg: str, path: Path) -> str:
    ffprobe = shutil.which("ffprobe") or ffmpeg.replace("ffmpeg", "ffprobe")
    proc = _run(
        [
            ffprobe, "-v", "error", "-show_entries", "stream=width,height:format=duration",
            "-of", "json", str(path),
        ]
    )
    if proc.returncode != 0:
        return "?"
    data = json.loads(proc.stdout)
    stream = data["streams"][0]
    duration = float(data["format"]["duration"])
    size_mb = path.stat().st_size / 1_000_000
    return f"{stream['width']}x{stream['height']} {duration:.1f}s {size_mb:.2f}MB"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="docs/media", type=Path)
    parser.add_argument(
        "--reduced-motion",
        choices=("reduce", "no-preference"),
        default="reduce",
        help=(
            "prefers-reduced-motion for the capturing browser. Default 'reduce' with "
            "?view=3d: the 3D scene is on screen and repaints on state changes only. "
            "'no-preference' records the idle camera drift as well, which costs about "
            "8MB of GIF and shows nothing extra."
        ),
    )
    parser.add_argument("--keep-webm", action="store_true", help="keep the raw playwright capture")
    args = parser.parse_args()

    out_dir = (REPO_ROOT / args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    video_dir = out_dir / ".capture"
    video_dir.mkdir(exist_ok=True)

    with httpx.Client(base_url=API_URL, timeout=20.0) as client:
        try:
            ffmpeg = check_ffmpeg()
            check_reachable(client)
            check_mock_llm()
            print("preflight ok, quiescing the stack")
            quiesce(client)
            source, offset = capture(client, video_dir, args.reduced_motion)
            print(f"captured {source.name}, trimming {offset:.2f}s of load off the front")
        except Preflight as exc:
            print(f"record_demo: {exc}", file=sys.stderr)
            return 1
        finally:
            # The latency toxic is still installed on purpose; the recording
            # is over, so take it back out.
            for scenario in SCENARIOS:
                client.delete(f"/api/chaos/{scenario}")

        gif, mp4 = out_dir / "demo.gif", out_dir / "demo.mp4"
        try:
            encode_gif(ffmpeg, source, offset, gif)
            encode_mp4(ffmpeg, source, offset, mp4)
        except Preflight as exc:
            print(f"record_demo: {exc}", file=sys.stderr)
            return 1

    print(f"{gif.relative_to(REPO_ROOT)}  {probe(ffmpeg, gif)}")
    print(f"{mp4.relative_to(REPO_ROOT)}  {probe(ffmpeg, mp4)}")
    if not args.keep_webm:
        shutil.rmtree(video_dir, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
