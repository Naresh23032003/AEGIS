// REST client for core-api. plan/02-contracts.md, HTTP API. Every route
// here exists in that table (or, for /metrics/summary, was added to
// apps/core/aegis/api.py in this same phase, see PHASE_4_REPORT.md).

import type {
  ActionRecord,
  CatalogEntry,
  EventEnvelope,
  IncidentDetail,
  MetricsSummary,
} from "./types";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080";

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`GET ${path} -> ${res.status}`);
  }
  return (await res.json()) as T;
}

async function postJSON<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, detail.detail ?? res.statusText);
  }
  return (await res.json()) as T;
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export interface IncidentSummary {
  id: string;
  title: string;
  severity: "sev1" | "sev2" | "sev3" | null;
  status: string;
  source_rule: string;
  affected_services: string[];
  started_at: string;
  resolved_at: string | null;
  mttr_seconds: number | null;
  autonomy: "auto" | "approved" | "escalated" | null;
  summary: string | null;
}

export function listIncidents(params?: { status?: string; limit?: number }) {
  const q = new URLSearchParams();
  if (params?.status) q.set("status", params.status);
  if (params?.limit) q.set("limit", String(params.limit));
  const qs = q.toString();
  return getJSON<IncidentSummary[]>(`/api/incidents${qs ? `?${qs}` : ""}`);
}

export function getIncident(id: string) {
  return getJSON<IncidentDetail>(`/api/incidents/${id}`);
}

export function getIncidentEvents(id: string) {
  return getJSON<EventEnvelope[]>(`/api/incidents/${id}/events`);
}

export function verifyChain(id: string) {
  return getJSON<{ valid: boolean; break_at_seq: number | null }>(
    `/api/incidents/${id}/verify-chain`,
  );
}

export function getCatalog() {
  return getJSON<Record<string, CatalogEntry>>("/api/catalog");
}

export function getMetricsSummary() {
  return getJSON<MetricsSummary>("/api/metrics/summary");
}

export function injectChaos(scenario: string) {
  return postJSON<EventEnvelope>(`/api/chaos/${scenario}`, {});
}

export async function clearChaos(scenario: string) {
  const res = await fetch(`${API_URL}/api/chaos/${scenario}`, { method: "DELETE" });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, detail.detail ?? res.statusText);
  }
  return (await res.json()) as EventEnvelope;
}

export function registerKey(pubkey: string, label: string) {
  return postJSON<{ pubkey: string; label: string }>("/api/keys", { pubkey, label });
}

export interface SignedDecisionBody {
  decision: "approve" | "reject" | "veto";
  pubkey: string;
  signed_payload: string;
  signature: string;
}

export function postApproval(actionId: string, body: SignedDecisionBody) {
  return postJSON<EventEnvelope>(`/api/approvals/${actionId}`, body);
}

export function postVeto(actionId: string, body: SignedDecisionBody) {
  return postJSON<EventEnvelope>(`/api/veto/${actionId}`, body);
}

export type { ActionRecord };
