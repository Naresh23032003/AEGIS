# 03. Agents, action catalog, policy

## Detection (deterministic, no LLM)

core-worker loop every 5 seconds. Rules in `apps/core/aegis/detection/rules.yaml`:

```yaml
rules:
  - id: latency_p95
    query: p95_latency            # named query from plan/02
    threshold_ms: 1000
    sustain_seconds: 15
  - id: error_rate
    query: error_rate
    threshold: 0.10
    sustain_seconds: 15
  - id: service_down
    probe: healthz
    fail_count: 3
```

A firing rule opens at most one incident per (rule, service) pair; dedupe while an incident is open. Detection also closes the loop for verification (same probes).

## Agent graph (LangGraph StateGraph, one durable run per incident)

State object (Pydantic, in packages/contracts):

```
IncidentState:
  incident: Incident
  evidence: list[Evidence]        # log lines, metric snapshots, trace summaries, each with source ref
  hypothesis: str | None
  proposed_actions: list[ActionProposal]
  executed_actions: list[str]
  verification: VerifyResult | None
  loop_count: int                 # hard max 3
  confidence: float               # 0..1, set by diagnosis
```

Nodes and edges:

```
triage -> diagnose -> plan_remediation -> gate -> execute -> verify
verify --pass--> resolve
verify --fail--> rollback -> diagnose        (loop_count += 1)
loop_count > 3 -> escalate
```

`gate` is not an LLM node. It calls OPA, opens veto windows, or waits on approval (LangGraph interrupt; the run parks durably in Postgres until POST /approvals resumes it). This is the human-in-the-loop checkpoint and the reason checkpoints exist, so treat interrupts carefully in code review.

### Node specs

| Node | Model | Tools | Output contract |
|---|---|---|---|
| triage | LLM_SMALL | none (gets detection snapshot) | severity, affected_services, one-line summary |
| diagnose | LLM_LARGE | query_logs (Loki), query_metrics (Prometheus), query_traces (Tempo), list_recent_changes (git log of target configs), get_container_stats | hypothesis + confidence + evidence refs |
| plan_remediation | LLM_LARGE | get_catalog | 1..2 ActionProposals, each referencing a catalog_key, with reasoning and rollback_key |
| execute | none | executor RPC | per plan/04 |
| verify | LLM_SMALL | detection probes | VerifyResult with evidence |
| supervisor | none (code) | | see below |

All LLM nodes use structured output (tool-use forced JSON matching the contracts). A schema-invalid response is retried once, then the run fails and the supervisor takes over. Every tool call and thought summary is emitted as an `agent.step` event, capped lengths per plan/02.

Prompt files live in `apps/core/aegis/agents/prompts/*.md`, one per node, with the contract JSON schema inlined. Keep prompts short and factual; no personas.

### Supervisor (code, not LLM)

Watches agent_runs.last_heartbeat (heartbeat every 10s from running nodes). If a run misses 3 heartbeats or fails schema validation twice: emit agent.quarantined, attempt one resume from the last checkpoint; if that fails, emit incident.escalated. The supervisor never calls an LLM.

### Mock mode (MOCK_LLM=1)

The LLM client (OpenAI SDK pointed at https://api.groq.com/openai/v1, auth via GROQ_API_KEY) is wrapped in one module, `aegis.llm`. Model ids come from LLM_SMALL and LLM_LARGE env vars. With MOCK_LLM=1 it serves recorded fixtures from `apps/core/fixtures/<scenario>/<node>_<n>.json`, keyed by scenario and call order. Record fixtures from real runs with `make record-fixtures SCENARIO=latency`. CI and the offline demo run entirely on fixtures. This must be built in phase 2, not retrofitted.

## Action catalog (closed set)

`apps/core/aegis/actions/catalog.yaml`. Agents can only reference these keys; the executor maps each key to an exact command. Free-form commands are structurally impossible.

| catalog_key | Tier | Effect | Rollback |
|---|---|---|---|
| restart_service | green | docker restart of one target container | none needed |
| clear_cache | green | FLUSHDB on shop cache keyspace | none |
| remove_toxic | green | delete a named Toxiproxy toxic | re-add (test only) |
| restart_dependency | yellow | restart redis or toxiproxy container | none |
| scale_service | yellow | compose scale target service 1 -> 2 | scale back to 1 |
| rollback_config | yellow | restore last good config file for a target service + restart | re-apply previous |
| flush_queue | red | destructive: purge orders retry queue | none (irreversible) |
| restart_database | red | restart shop-db | none |

Params schemas per key live next to the catalog. `service` params are validated against the fixed list of target services.

## Risk tiers

| Tier | Behavior |
|---|---|
| green | Auto-execute after OPA allow. Event trail only. |
| yellow | OPA allow -> action.veto_window_opened (30s). Console shows countdown card. Signed veto cancels; timeout executes. |
| red | Blocks on signed approval. LangGraph interrupt parks the run. No timeout; escalates to incident.escalated after 15 minutes unanswered. |

## OPA policy (packages/policies)

Package `aegis.actions`, entry `decision` returning `{allow, rule_id, reason}`. Input document:

```json
{
  "action": {"catalog_key": "...", "params": {}, "tier": "...", "confidence": 0.85},
  "incident": {"severity": "sev2", "loop_count": 1, "actions_executed": 1},
  "context": {"env": "demo"}
}
```

Rules to implement (each with an opa test in packages/policies/tests):

1. deny if catalog_key not in catalog (defense in depth; executor also checks)
2. deny if confidence < 0.6
3. deny if incident.actions_executed >= 5 (runaway brake)
4. deny red tier when severity is sev3 (low) because risk exceeds impact
5. deny scale_service if already scaled (params carry current state)
6. default deny; allow only via explicit rules per tier

The worker calls OPA over HTTP for every proposal and emits action.policy_checked with the rule id either way. The console policy page renders the catalog and these rules from GET /catalog so a viewer can see that denial is structural.

## Chaos scenarios (fixed set of five)

| scenario key | Injection | Expected diagnosis | Expected fix path |
|---|---|---|---|
| latency | Toxiproxy adds 1500ms latency on orders -> shop-db | DB latency on orders | remove_toxic (green) |
| crash | docker stop target-payments | payments down | restart_service (green) |
| error_spike | payments flag makes 50% of requests 500 | bad config/flag on payments | rollback_config (yellow) |
| memory_leak | payments endpoint allocates until container OOMs | memory growth then crash loop | restart_service + note in summary |
| cache_outage | pause redis container | cache dependency down, latency spike | restart_dependency (yellow) |

Each scenario has an e2e test asserting: incident detected within 30s of injection, resolved with expected autonomy level, MTTR under 90s (fixtures) or 150s (live LLM), hash chain valid, expected catalog_key executed. These five tests are the project's definition of working.
