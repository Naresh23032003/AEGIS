# 01. Architecture

## Locked stack

| Layer | Choice | Version pin |
|---|---|---|
| Frontend | Next.js (App Router), TypeScript, Tailwind, shadcn/ui | Next 15.x |
| Motion | motion (Framer Motion successor) | latest 12.x |
| 3D | @react-three/fiber + drei + postprocessing | R3F 9.x |
| 2D fallback graph | @xyflow/react (React Flow) | 12.x |
| Command palette | cmdk | latest |
| Agent service | Python 3.12, FastAPI, LangGraph | LangGraph 0.6+ |
| LangGraph persistence | AsyncPostgresSaver (checkpoints in Postgres) | |
| LLM | Groq API via the OpenAI-compatible endpoint. Two roles set by env: LLM_SMALL (default llama-3.1-8b-instant) for triage and verify, LLM_LARGE (default llama-3.3-70b-versatile) for diagnosis and remediation. All calls go through the aegis.llm module so the vendor is swappable in one file | |
| Event transport | Redis Streams | Redis 7 |
| Database | Postgres 16 | |
| Policy | Open Policy Agent, Rego | OPA latest stable |
| Telemetry | OpenTelemetry SDKs, exported to grafana/otel-lgtm all-in-one container | |
| Fault injection | Toxiproxy (network faults) plus app-level fault endpoints | |
| Container runtime | Docker Compose, single file | |
| CI | GitHub Actions | |

Do not add Temporal, Kafka, NATS, ClickHouse, Kubernetes, or gVisor. The reasons are recorded as ADRs (summaries below, full text written in phase 0).

## Monorepo layout

```
AEGIS/
├── apps/
│   ├── console/            Next.js frontend
│   ├── core/               FastAPI API + agent worker + executor (one Python package, three entrypoints)
│   └── target/             demo system that gets broken and healed
│       ├── gateway/        public API, calls orders and payments
│       ├── orders/         talks to shop Postgres through Toxiproxy
│       └── payments/       has fault endpoints (memory leak, error spike)
├── packages/
│   ├── contracts/          JSON Schema source of truth; generated Pydantic models and TS types
│   └── policies/           Rego files + OPA tests
├── deploy/
│   ├── docker-compose.yml
│   ├── otel/               collector config if needed
│   └── grafana/            provisioned dashboards
├── docs/
│   ├── adr/                ADR-001 .. ADR-008
│   ├── reports/            PHASE_N_REPORT.md files
│   └── architecture.md     rendered diagram + prose
├── e2e/                    scenario test suite (pytest)
├── design-system/          MASTER.md + page overrides (see plan/05)
├── Makefile
├── CLAUDE.md
└── README.md
```

apps/core is one Python project with three entrypoints so imports stay shared:

- `aegis.api` FastAPI app: REST + WebSocket fanout
- `aegis.worker` detection loop + LangGraph agent runs + supervisor
- `aegis.executor` the only process allowed to touch the Docker socket

## Runtime topology (docker compose services)

| Service | Image/build | Port (host) | Notes |
|---|---|---|---|
| console | apps/console | 3000 | |
| core-api | apps/core | 8080 | REST + WS |
| core-worker | apps/core | none | detection, agents, supervisor |
| core-executor | apps/core | internal 8090 | Docker socket mounted, allowlist only |
| target-gateway | apps/target/gateway | 9000 | traffic generator hits this |
| target-orders | apps/target/orders | internal 9001 | DB via Toxiproxy |
| target-payments | apps/target/payments | internal 9002 | fault endpoints |
| shop-db | postgres:16 | internal 5432 | demo data |
| aegis-db | postgres:16 | internal 5433 | incidents, events, checkpoints |
| shop-redis | redis:7 | internal 6379 | demo shop cache only; the only Redis any catalog action may touch |
| aegis-redis | redis:7 | internal 6379 | AEGIS event stream; never in the action catalog, unreachable by agents |
| opa | openpolicyagent/opa | internal 8181 | loaded with packages/policies |
| toxiproxy | ghcr.io/shopify/toxiproxy | internal 8474 | proxies orders -> shop-db |
| lgtm | grafana/otel-lgtm | 3001 (Grafana) | OTLP 4317/4318 |
| loadgen | small Python container | none | constant realistic traffic at gateway |

Data flow for one incident:

1. loadgen sends traffic; all target services export OTel traces, metrics, logs to lgtm.
2. core-worker probes target health endpoints and queries Prometheus (inside lgtm) every 5 seconds. Rule-based anomaly detection fires (see plan/03).
3. Worker opens an incident row, appends incident.detected to the Postgres event log (hash chained), publishes it on aegis-redis stream `aegis:events`.
4. Worker starts a LangGraph run: triage -> diagnose -> plan -> act -> verify, with loop back to diagnose (max 3 loops).
5. Every proposed action goes to OPA. Green tier executes via core-executor. Yellow tier opens a 30 second veto window. Red tier blocks on a signed approval from the console.
6. Verification re-probes for up to 60 seconds. Pass closes the incident with MTTR recorded. Fail triggers rollback and another loop, then human escalation.
7. core-api tails the aegis-redis stream and fans out every event to console WebSocket clients. The console renders the whole battle live and can replay it later from the Postgres event log.

## ADR summaries (write full ADRs in phase 0)

- ADR-001: LangGraph Postgres checkpoints instead of Temporal. Durability at demo scale without a second orchestrator. Temporal noted as the production path.
- ADR-002: Executor allowlist + hardened containers instead of gVisor. gVisor is Linux-only and would break the one-command demo on macOS.
- ADR-003: Redis Streams instead of Kafka/NATS. One container for the bus (aegis-redis, separate from the shop cache), consumer groups are enough at this scale.
- ADR-004: Rule-based detection, LLM diagnosis. Detection must be deterministic and cheap; reasoning is where the LLM earns its cost.
- ADR-005: Closed action catalog. Agents choose from typed, pre-audited actions. Free-form shell is never possible, even if the model asks.
- ADR-006: Browser-held Ed25519 keys for approvals. The server verifies but cannot forge an approval.
- ADR-007: Recorded LLM fixtures (MOCK_LLM=1) so the demo runs offline and deterministically.
- ADR-008: R3F topology with automatic 2D React Flow fallback on WebGL failure or `?view=2d`.
