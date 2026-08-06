# LinkedIn: follow-up post (one week after launch)

Post this roughly a week after the launch post. Fill in {N} once actual
engagement/replies exist; do not guess a number ahead of time.

---

A week ago I posted AEGIS, a self-healing ops platform that proves what
it did instead of just claiming it. A few notes on what building it
actually taught me, past the demo.

The eight architecture decisions I'd make again, and why, are written up
as ADRs rather than left implicit: LangGraph checkpoints over standing up
a second orchestrator for a demo-scale system
(docs/adr/ADR-001-langgraph-postgres-checkpoints.md), a closed action
catalog so the model chooses from typed actions and never gets near a
shell (docs/adr/ADR-005-closed-action-catalog.md), Ed25519 keys held in
the browser so the server can verify an approval but never forge one
(docs/adr/ADR-006-browser-held-ed25519-keys.md).

The thing that surprised me most wasn't the agent loop, it was the policy
gate. Watching a live LLM diagnosis come back at 50% confidence and get
denied outright, escalating to a human instead of executing anyway, made
the safety design feel real in a way no unit test had. That single
behavior is doing more work than the whole remediation loop combined.

Full write-up and all eight ADRs: github.com/Naresh23032003/AEGIS/tree/main/docs/adr

#incidentresponse #llmagents #softwarearchitecture
