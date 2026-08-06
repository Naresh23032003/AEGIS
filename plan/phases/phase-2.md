# Phase 2 brief: Agent loop end to end

Goal: the heart of the project. A durable LangGraph run heals the latency and crash scenarios with a real LLM, and MOCK_LLM=1 replays recorded fixtures deterministically.

## Read (in this order, nothing else)

1. CLAUDE.md
2. This file
3. plan/06-milestones.md, "Phase 2" section
4. plan/03-agents-and-policy.md, all of it except the OPA rules subsection (gate calls OPA in phase 3; this phase the gate node passes green tier through and logs a stub allow)
5. plan/02-contracts.md, "Event catalog" and "Database schema" (agent_runs, actions) sections
6. plan/04-security.md, "Executor sandbox" and "Prompt injection defense" sections
7. plan/01-architecture.md, data flow steps 4-6

## Build order

1. Contracts first: extend packages/contracts with any agent-facing schemas listed in plan/03 not yet generated (ActionProposal, Evidence, VerifyResult). `make contracts`.
2. aegis.llm wrapper: one module owning the LLM client (OpenAI SDK, base_url https://api.groq.com/openai/v1, GROQ_API_KEY, models from LLM_SMALL and LLM_LARGE per plan/03), structured tool-use output, retry-once-on-invalid-schema, token/cost accounting into agent_runs, and the MOCK_LLM fixture player. Build the fixture player now, record later. If LLM_LARGE fails schema validation repeatedly during prompt iteration, try moonshotai/kimi-k2-instruct or openai/gpt-oss-120b via the env var before touching the wrapper code, and note the final choice in the phase report.
3. Executor service: catalog.yaml, param validation, docker SDK mappings for green actions (restart_service, clear_cache, remove_toxic), shared-secret auth, action.executed events. Move the phase 1 chaos container helpers in here.
4. Diagnosis tools (Loki, Prometheus, Tempo HTTP APIs inside lgtm, container stats) with quarantine wrapping, truncation, ANSI stripping, email masking.
5. The graph: nodes and edges per plan/03, AsyncPostgresSaver, heartbeats to agent_runs, agent.step events from every node, loop_count cap, escalation path.
6. Supervisor: heartbeat watcher, quarantine, one resume attempt, escalate. Unit test with a stubbed hung node.
7. Live runs: heal latency, then crash. Iterate on prompts in apps/core/aegis/agents/prompts/ until both heal reliably three times in a row.
8. `make record-fixtures SCENARIO=latency` (and crash); wire e2e for both scenarios on fixtures; checkpoint-resume test (kill worker mid-run, restart, run completes).

## Gotchas

- The gate node is code, not LLM, and in this phase only handles green tier plus a hardcoded allow log; leave clear TODO-free seams for OPA and interrupts (they land in phase 3, do not build them early).
- Fixture keying is (scenario, node, call_index). Diagnosis may call tools a variable number of times; record whole node-level LLM exchanges, not tool results (tools stay live even in mock mode, they are deterministic against the injected fault).
- Cost accounting: prices in one config dict, computed per run, summed per incident.
- Groq free tier rate limits: the wrapper must back off on 429 (exponential, max 3 retries) or live runs will flake.
- verify uses the phase 1 detection probes, not new logic.

## Exit ritual

Acceptance from plan/06 phase 2 (including the resume test), PHASE_2_REPORT.md with pasted e2e output and three consecutive live heal timings, branch/tag phase-2, push, stop.
