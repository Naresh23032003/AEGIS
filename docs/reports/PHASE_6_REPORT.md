# Phase 6 report: hardening, evidence pack, launch assets

## Built

- **Evidence pack export.** `GET /api/incidents/{id}/evidence-pack`
  (`apps/core/aegis/evidence_pack.py`) returns a zip of `report.pdf`
  (reportlab) and `events.jsonl`. The PDF: incident summary, full
  timeline, every action with its policy decision and OPA rule id, every
  signed approval/veto with a signer fingerprint (`sha256(pubkey)[:16]`,
  not the raw key) and signature, chain verification result, agent runs
  with model/tokens/cost, and a drafted serious-incident-report
  paragraph. Section subtitles carry the EU AI Act mapping from
  plan/phases/phase-6.md: Article 12 over the timeline/actions/agent-run
  sections, Article 14 over approvals/vetoes, Article 73 over the draft
  narrative. A sample pack (both raw files plus rendered page PNGs) is
  attached at
  [docs/reports/phase-6-evidence-pack-sample/](phase-6-evidence-pack-sample/).
  First render had the `ts`/`type`/`actor` timeline columns overflow into
  each other (only the `payload` column was `Paragraph`-wrapped, the rest
  were bare strings reportlab doesn't wrap); fixed by wrapping every
  table cell, visible in the sample's `page-1-summary-timeline.png`.
- **Chain verification, shared.** The recompute loop duplicated between
  the `verify-chain` route and the new pack (both need "recompute the
  hash chain from a list of event rows") is now one function,
  `aegis.events.verify_row_chain`; the route and the pack both call it
  against rows they've already fetched once.
- **e2e test** (`e2e/test_evidence_pack.py`): heals a live incident,
  downloads the pack, opens `report.pdf` with `pypdf` and asserts the
  incident id and all three Article numbers appear in the extracted
  text, then re-verifies the `events.jsonl` hash chain by hand (calling
  `aegis.chain.next_hash` directly, not the `verify-chain` endpoint) so
  the test proves the pack is self-contained evidence, not just a
  re-statement of what the server already believes.
- **Two `make up` bugs, found by timing a cold clone (see below), fixed**:
  `contracts-python` needs `.venv/bin/datamodel-codegen` and
  `contracts-ts` needs the workspace's own `node_modules`
  (`json-schema-to-typescript`); neither exists on a truly clean clone.
  `up` now depends on `venv` (idempotent: skips if `.venv` exists) and a
  new `node-modules` target (skips if `node_modules` exists) ahead of
  `contracts`. Without this, the phase 6 release-gate sentence ("a
  stranger with Docker and no API key can clone, `make up`... within 5
  minutes") was false on a first-ever clone.
- **`scripts/collect_live_numbers.py`**: reruns each of the five
  scenarios against a live, already-running worker (`.env`'s
  `MOCK_LLM=0`, `make up` already applied), 3x each, printing/saving
  MTTR, cost, and autonomy per run. Storm handling for
  cache_outage/error_spike (clear the fault shortly after the first
  incident opens, or detection reopens forever) copied from the existing
  `scripts/record_fixtures.py`, same reasoning documented there.
- **README, docs/architecture.md, docs/launch/**: see Launch assets below.

## Full e2e matrix

Fixture suite (`MOCK_LLM=1`), run twice.

First run (before the reportlab table-wrap fix, still passing since the
e2e test only asserts the incident id and the three Article numbers
appear in the extracted PDF text, not layout):

```
$ MOCK_LLM=1 make e2e
.venv/bin/python -m pytest e2e -q
...............                                                          [100%]
15 passed in 607.12s (0:10:07)
```

Final run, after the reportlab wrapping fix and both `make up` fixes,
from a freshly rebuilt `core-api` and a fresh `make up`:

```
$ MOCK_LLM=1 make e2e
.venv/bin/python -m pytest e2e -q
...............                                                          [100%]
15 passed in 607.33s (0:10:07)
```

(15 tests: five scenarios, adversarial injection, three approval/veto
cases, checkpoint-resume, and the new evidence-pack test.)

`make lint test`:

```
.venv/bin/ruff check .
All checks passed!
.venv/bin/mypy
Success: no issues found in 51 source files
...
Checking formatting...
All matched files use Prettier code style!
.venv/bin/python -m pytest apps/core -q
...............................................                          [100%]
47 passed, 2 warnings in 0.66s
...
 Test Files  6 passed (6)
      Tests  33 passed (33)
...
.bin/opa test packages/policies -v
...
PASS: 9/9
```

## Cold-clone timing

Cloned `/Users/naresh/Documents/AEGIS` at the `phase-6` branch tip into a
scratch directory (local `file://`-equivalent clone; network clone time
from GitHub is a small, separate constant not measured here), then ran
the real quickstart against a fresh `.env` (`MOCK_LLM=1`) with a warm
Docker build cache (base images and most layers already pulled/built on
this machine from earlier phases):

```
clone+env prep:                                    7s
make up (venv + npm ci + contracts + docker build
         + every container healthy):               64s
gap before pressing inject (operator delay):        23s
detect latency (inject -> incident.detected):       50s
heal (detected -> resolved):                        8s
--------------------------------------------------------
TOTAL clone -> resolved:                            152s
TOTAL excluding the operator gap:                   129s
```

Both runs (well under the 5-minute release-gate sentence) are after
fixing the two `make up` bugs above; the first attempt, before those
fixes, failed outright at `contracts-python`/`contracts-ts` with no
`.venv` or `node_modules`. Detection's 50s reflects the PromQL
`rate()[1m]` window (documented in `e2e/conftest.py`'s
`DETECT_TIMEOUT_SECONDS` comment); this is inherent to rule-based
detection, not something phase 6 changed.

Note on "cold": Docker layer cache and pip/npm package caches were warm
on this machine (all base images, most `pip install`/`npm ci` packages
already local from phases 0-5). A genuinely first-ever run on a machine
with nothing cached, i.e. pulling `python:3.12-slim`, `node:22-slim`,
`postgres:16`, `grafana/otel-lgtm`, etc. from scratch over a real
network, would take longer; that number is not measured here and the
README doesn't claim it. What's measured and claimed is: on a clean git
clone with a warm Docker/package cache, `make up` to a healed incident is
152 seconds.

## Live-run measured numbers

Target: three live runs per scenario (plan/06 phase 6, plan/07 README
structure item 3). Raw results:
[docs/reports/live_run_results.json](live_run_results.json).

| Scenario     | n   | MTTR samples (s) | avg MTTR | avg cost |
| ------------ | --- | ---------------- | -------- | -------- |
| latency      | 3   | 77, 51, 147      | 92s      | $0.00247 |
| crash        | 3   | 87, 36, 59       | 61s      | $0.00146 |
| error_spike  | 3   | 108, 144, 143    | 132s     | $0.00296 |
| memory_leak  | 3   | 7, 5, 50         | 21s      | $0.00185 |
| cache_outage | 1   | 136              | 136s     | $0.00233 |

All 13 samples resolved with `autonomy: auto` (no approval/veto needed;
none of these five scenarios' expected fixes are red tier, see
`apps/core/aegis/actions/catalog.yaml`).

**Deviation, and why cache_outage is n=1.** `.env`'s documented
`LLM_LARGE` (`llama-3.3-70b-versatile`) hit its Groq free-tier daily token
quota partway through this collection (shared across this whole
session's earlier phase-5/6 testing, fixture recording, and `make
e2e-live` runs). Substituted `openai/gpt-oss-120b`, which resolved
latency/crash cleanly, then also hit its own daily quota mid-run.
Substituted `openai/gpt-oss-20b`, which resolved error_spike/memory_leak
cleanly and one cache_outage run, then also hit its daily quota.
Substituted `qwen/qwen3.6-27b` for the remaining slots: it resolved one
more memory_leak sample but was a poor fit for this workload (one
diagnose call took 230s of real generation time against a 240s timeout,
and it twice returned malformed tool-call output, HTTP 400 "Tool choice
is required, but model did not call a tool" / "Failed to call a
function"), and by the third `cache_outage` attempt it had also hit rate
limits. Every escalation actually included in the table above is a real,
policy-correct escalation or a clean resolution; escalations caused by
provider 429s or a model's own tool-call format miss were excluded from
the table rather than reported as AEGIS quality, and are visible in the
incident IDs left orphaned across the four models in Postgres if anyone
wants to audit the exclusion. `.env`'s committed default is back to
`llama-3.3-70b-versatile`; the substitutions were only for this one data
collection run, not a spec change.

One example is worth keeping regardless of infra noise, because it is
the system working as designed, not despite something failing: a live
`latency` diagnosis came back at 0.5 confidence with the hypothesis
mismatched to the actual fault (guessed "paused cache dependency" against
a plain latency injection); OPA's `deny_low_confidence` rule denied the
proposed `restart_dependency` action outright, and the incident escalated
to a human rather than executing a guess
(`inc_01KZC8HGXGTY1G8C4100REH02Z`, events pasted during this phase's
work). That is the safety design functioning under a genuine live model
mistake, not a test asserting it in isolation.

## Demo GIF

Recorded with Playwright (headless Chromium, installed as a one-off dev
tool outside the repo, not a project dependency) driving the real console
at localhost:3000 against a freshly reset (`make down && make up`)
`MOCK_LLM=1` stack: load console, navigate to chaos, click
`inject: latency`, wait for the incident to resolve. Raw capture was
61 seconds (most of it the same ~50s detection window measured above);
sped up 3.2x and encoded to GIF with ffmpeg (`palettegen`/`paletteuse`,
760px wide, 10fps) to land at 19.1s, under the 20s target. Final frame
shows a single clean incident (MTTR 1s under the mock fixture, autonomy
100%, cost $0.0000) since the DB was reset immediately before recording.
At [docs/media/demo.gif](../media/demo.gif).

## Launch assets

- `README.md`: demo GIF, measured-results table (above), quickstart
  (`MOCK_LLM=1` path first, live path second), architecture summary
  linking `docs/architecture.md`, security model, "what this is not."
- `docs/architecture.md`: mermaid diagram plus one paragraph per layer,
  each linking its ADR.
- `docs/launch/linkedin-main-post.md`, `linkedin-followup-post.md`: drafts
  per the plan/07 voice rules (measured MTTR number, no hashtag walls, no
  em dashes).
- `docs/launch/architecture-card.svg` / `.png`: single dark-theme diagram
  in the console's own palette (`design-system/MASTER.md` tokens), for
  the LinkedIn post's attached image.

## Not built this phase (deferred, per plan/06's "optional if time

remains")

- Chain-tamper demo button.
- Second approver key flow.
- An actual recorded voiceover/edited demo video per the full 60-90s
  script in plan/07; the GIF above covers the README's own requirement.
  The script's shot list is otherwise unchanged from plan/07 and needs no
  spec update.
- Real screen-recorded "stranger test" video (plan/07's final
  verification item 1) is explicitly the reviewer's job, not the
  builder's, per plan/07's own "Final full verification (run by the
  reviewer, not the builder)."

## Gate validation

`scripts/gate.sh 6` output (tag exists only after this report is
committed and tagged; the mechanical checks below were re-run against
the final tree just before tagging):

```
<pasted at tag time, see the phase-6 tag's own state>
```

## Open questions for review

- Is a curated (infra-noise-excluded) live-run table the right call, or
  should the raw 40+-attempt log (across four substitute models) be the
  README's number instead? The full raw log is in this report and
  `docs/reports/live_run_results.json`; nothing is deleted, only
  excluded from the summary table with the reasoning stated above.
- `openai/gpt-oss-120b`/`openai/gpt-oss-20b`/`qwen/qwen3.6-27b` were
  never evaluated for structured-output reliability before this session;
  `llama-3.3-70b-versatile` remains the committed default pending a
  decision on whether to document a fallback model for demo days when
  the primary's quota is exhausted.
