# Roadmap

Future work items for AEGIS sourced from architectural decisions and project plans.

## 1. Kubernetes executor

The current executor operates directly against the local Docker socket on a single host (`README.md`, `plan/07-review-and-launch.md`, `docs/adr/ADR-002-executor-allowlist-not-gvisor.md`). A production deployment needs an executor targeting Kubernetes resources across namespaces rather than communicating with a daemon socket. This item builds a Kubernetes executor service that translates catalog actions into Kubernetes API calls (such as rolling restarts, deployment rollbacks, and pod evictions) while preserving the allowlist model and quarantine boundaries.

Done when: catalog actions execute against target pods and workloads via Kubernetes API calls without requiring Docker socket access.

## 2. Temporal workflow migration

Incident orchestration runs on LangGraph graphs checkpointed into PostgreSQL via `AsyncPostgresSaver` (`README.md`, `docs/adr/ADR-001-langgraph-postgres-checkpoints.md`, `plan/07-review-and-launch.md`). LangGraph checkpoints provide durability across single-process restarts but lack built-in support for child workflows, cron schedules, cross-worker queue routing, and external workflow inspection tooling. Migrating orchestration to Temporal workflows gives the system durable distributed execution across many worker pools.

Done when: incident runs execute as Temporal workflows and activities rather than LangGraph checkpointed transitions in PostgreSQL.

## 3. WebAuthn and passkey approvals

Human approvals and vetoes currently rely on browser-generated Ed25519 keypairs stored in IndexedDB (`README.md`, `docs/adr/ADR-006-browser-held-ed25519-keys.md`, `plan/04-security.md`, `plan/07-review-and-launch.md`). This proves that the server did not forge the approval, but does not bind the signature to a hardware-backed operator credential or an enterprise identity provider. Moving to WebAuthn and passkeys adds hardware binding and per-user identity without weakening the non-forgeability property.

Done when: red tier approvals and yellow tier vetoes verify WebAuthn passkey signatures produced by hardware-backed authenticators.

## 4. Expanded action catalog

The remediation agent currently selects from a closed catalog of eight pre-audited actions (`README.md`, `docs/adr/ADR-005-closed-action-catalog.md`). Faults outside this scope cannot be resolved autonomously and must be escalated to human operators. Expanding the catalog introduces additional typed actions (such as draining connections, clearing deadlocks, or scaling downstream replicas) with schema validation and OPA tier assignments while maintaining isolation from free-form shell execution.

Done when: additional catalog entries with typed schemas and OPA policy rules execute without enabling arbitrary shell command execution.

## 5. Re-record latency fixture after verification threshold fix

In `apps/core/aegis/agents/tools.py`, line 309 builds the probe threshold map keyed by rule ID (`latency_p95`), while line 320 looks up thresholds using the query key (`p95_latency`), causing the latency threshold check to be skipped (`README.md`, `docs/reports/FINAL_VERIFICATION.md` phase 13 defect 18). Once the lookup key is corrected so latency probes evaluate properly against the threshold, the latency fixture must be re-recorded with `make record-fixtures SCENARIO=latency` to reflect the fixed probe output.

Done when: probe threshold comparisons match query keys to rule configurations, and re-recorded latency fixtures allow `test_latency_heals` to pass in fixture mode.

## 6. v0.1.0 release tag and launch assets

Phase 7 outlined the launch checklist, demo video requirements, and release tagging (`plan/07-review-and-launch.md`). Moving the release tag requires clean test runs, finalized documentation, and published launch materials. This item tracks publishing the initial v0.1.0 release on GitHub alongside the walkthrough video and evidence pack verification scripts.

Done when: git tag `v0.1.0` is tagged on main with release notes and the demo video linked.
