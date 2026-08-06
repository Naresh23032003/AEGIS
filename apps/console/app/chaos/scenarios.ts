// Copy for the chaos panel. Transcribed from plan/03-agents-and-policy.md,
// "Chaos scenarios (fixed set of five)" -- the fixed set core-api's
// SCENARIOS constant (apps/core/aegis/chaos.py) actually accepts.

export interface ScenarioMeta {
  key: string;
  name: string;
  breaks: string;
  expectedResponse: string;
  fixPath: string;
}

export const SCENARIOS: ScenarioMeta[] = [
  {
    key: "latency",
    name: "latency",
    breaks: "Toxiproxy adds 1500ms latency on orders -> shop-db",
    expectedResponse: "DB latency on orders",
    fixPath: "remove_toxic (green)",
  },
  {
    key: "crash",
    name: "crash",
    breaks: "docker stop target-payments",
    expectedResponse: "payments down",
    fixPath: "restart_service (green)",
  },
  {
    key: "error_spike",
    name: "error spike",
    breaks: "payments flag makes 50% of requests 500",
    expectedResponse: "bad config/flag on payments",
    fixPath: "rollback_config (yellow)",
  },
  {
    key: "memory_leak",
    name: "memory leak",
    breaks: "payments endpoint allocates until container OOMs",
    expectedResponse: "memory growth then crash loop",
    fixPath: "restart_service + note in summary",
  },
  {
    key: "cache_outage",
    name: "cache outage",
    breaks: "pause redis container",
    expectedResponse: "cache dependency down, latency spike",
    fixPath: "restart_dependency (yellow)",
  },
];
