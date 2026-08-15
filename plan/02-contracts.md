# 02. Contracts

Source of truth lives in packages/contracts as JSON Schema files. Codegen produces Pydantic v2 models (datamodel-code-generator) and TypeScript types (json-schema-to-typescript). Both apps import generated code; nobody hand-writes a duplicate type. Regenerate with `make contracts`.

## Event envelope

Every event, on the Redis stream and in Postgres, uses this envelope:

```json
{
  "id": "01J...ULID",
  "ts": "2026-08-06T10:15:03.201Z",
  "type": "action.proposed",
  "incident_id": "inc_01J...",
  "actor": "agent:diagnosis | agent:remediation | system:detector | human:<pubkey8> | system:supervisor",
  "payload": { }
}
```

Rules: `id` is a ULID. `actor` is namespaced as shown. `payload` shape is defined per event type in packages/contracts/events/. Events are append-only and never mutated.

## Event catalog

| Type | Emitted by | Payload highlights |
|---|---|---|
| chaos.injected | api (chaos endpoint) | scenario, params |
| chaos.cleared | api | scenario |
| incident.detected | worker detector | rule, service, metrics snapshot |
| incident.classified | triage agent | severity (sev1..sev3), affected_services, summary |
| agent.run.started | worker | agent, model, checkpoint_id |
| agent.step | each agent | phase (observe/plan/act/verify), thought_summary (max 400 chars), tool, tool_args_redacted |
| agent.run.completed | worker | agent, tokens_in, tokens_out, cost_usd, duration_ms |
| agent.run.failed | worker | agent, reason |
| agent.quarantined | supervisor | agent, reason, recovery (resume/escalate) |
| action.proposed | remediation agent | action_id, catalog_key, params, tier, confidence, reasoning (max 600 chars), rollback_key, diagnosis_confidence |
| action.policy_checked | worker | action_id, decision (allow/deny), opa_rule_id |
| action.veto_window_opened | worker | action_id, closes_at |
| action.approval_requested | worker | action_id, diff, reasoning |
| action.approved | api | action_id, approver_pubkey, signature |
| action.rejected | api | action_id, approver_pubkey, signature, reason |
| action.executed | executor | action_id, result, duration_ms |
| action.rolled_back | executor | action_id, rollback_of |
| verify.passed | verification agent | evidence |
| verify.failed | verification agent | evidence, loop_count |
| incident.resolved | worker | mttr_seconds, autonomy (auto/approved/escalated), actions_taken |
| incident.escalated | worker | reason, loops_exhausted |

The console renders every one of these; do not add types the console will not render.

`action.proposed` carries two confidences and they are not interchangeable: `confidence` is the ActionProposal field (how sure the model is of this action), `diagnosis_confidence` is the diagnose node's confidence in the cause being acted on, copied out of IncidentState at propose time. It sits on the payload rather than inside `action-proposal.schema.json` because it is not a property of the proposal, and it is on this event rather than one of its own because no event type carried it before and the console needs both numbers on the same card.

## Database schema (aegis-db, schema `aegis`)

```sql
incidents(
  id text pk, title text, severity text, status text,           -- open|resolving|awaiting_approval|resolved|escalated
  source_rule text, affected_services text[],
  started_at timestamptz, resolved_at timestamptz,
  mttr_seconds int, autonomy text, summary text
)

incident_events(
  seq bigserial pk, incident_id text, event_id text unique,
  type text, actor text, payload jsonb,
  prev_hash text, hash text, created_at timestamptz
)
-- hash = sha256(prev_hash || canonical_json(envelope)); first event uses prev_hash = incident_id
-- one chain per incident; chain verified by GET /api/incidents/{id}/verify-chain

actions(
  id text pk, incident_id text, catalog_key text, params jsonb,
  tier text,                                                     -- green|yellow|red
  status text,                                                   -- proposed|denied|awaiting_approval|vetoed|executing|executed|failed|rolled_back
  confidence real, policy_result jsonb, reasoning text,
  proposed_by text, executed_at timestamptz, result jsonb
)

approvals(
  id text pk, action_id text, decision text,                     -- approve|reject
  approver_pubkey text, signed_payload text, signature text,
  created_at timestamptz
)

agent_runs(
  id text pk, incident_id text, agent text, status text,
  model text, tokens_in int, tokens_out int, cost_usd numeric(10,5),
  checkpoint_id text, started_at timestamptz, ended_at timestamptz,
  last_heartbeat timestamptz
)

approver_keys(pubkey text pk, label text, created_at timestamptz)
```

LangGraph checkpoint tables are created by AsyncPostgresSaver in the same database, separate schema `checkpoints`.

## HTTP API (core-api, prefix /api)

| Method + path | Purpose |
|---|---|
| GET /incidents?status=&limit= | list, newest first |
| GET /incidents/{id} | detail incl. actions and agent_runs |
| GET /incidents/{id}/events | full ordered event log (replay source) |
| GET /incidents/{id}/verify-chain | recomputes hash chain, returns {valid, break_at_seq?} |
| POST /approvals/{action_id} | body: {decision, pubkey, signed_payload, signature}; 400 on bad signature |
| POST /veto/{action_id} | body: same signed shape; only during open veto window |
| POST /keys | register approver pubkey {pubkey, label} |
| POST /chaos/{scenario} | inject; scenario in the fixed set of five |
| DELETE /chaos/{scenario} | clear fault manually |
| GET /chaos/{scenario} | {scenario, fault_present}; fault_present null when the chaos API cannot tell. Added in phase 9 so a test can assert a healed incident also left the fault gone. Not an agent input |
| GET /metrics/summary | MTTR trend, autonomy rate, escalation rate, cost per incident, per scenario |
| GET /catalog | action catalog with tiers (console renders policy table from this) |
| GET /incidents/{id}/evidence-pack | zip: regulator-styled PDF + events.jsonl (built in phase 6, spec in plan/phases/phase-6.md) |
| GET /healthz | liveness |

Signed payload for approvals and vetoes is the canonical JSON string of `{action_id, decision, ts}`; the server checks ts is within 60 seconds, verifies Ed25519 signature against a registered pubkey, then emits the event.

## WebSocket

`WS /ws/events`: server tails Redis stream `aegis:events` (consumer group per connection is unnecessary; use XREAD from $) and forwards envelopes as JSON text frames. On connect, client may send `{"replay_incident": "<id>"}` to receive that incident's full event log from Postgres first, then live events. Heartbeat ping every 20s.

## Prometheus queries used by detection (inside lgtm)

Defined in apps/core config, not hardcoded in Python:

- p95 latency per service: `histogram_quantile(0.95, sum(rate(http_server_duration_ms_bucket{service_name=~"target-.*"}[1m])) by (le, service_name))`
- error rate: `sum(rate(http_server_requests_total{status_code=~"5.."}[1m])) by (service_name) / sum(rate(http_server_requests_total[1m])) by (service_name)`
- container up: health endpoint probe (HTTP 200 within 2s)

Thresholds live in `apps/core/aegis/detection/rules.yaml` (see plan/03).
