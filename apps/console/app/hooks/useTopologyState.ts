// Renderer-agnostic topology state, shared by the React Flow fallback
// (this phase) and the R3F scene (phase 5) per plan/05-frontend.md,
// Topology scene (R3F), Fallback: "Both consume one useTopologyState()
// hook so they can never drift." Reads only from useVisibleEvents(), so
// it works unchanged in live and replay mode.
//
// Nodes are the fixed five from plan/01-architecture.md's runtime
// topology table (target-gateway, target-orders, target-payments,
// shop-db, redis); edges are the real call graph (gateway calls orders
// and payments; orders reaches shop-db through Toxiproxy and redis for
// cache). Traffic level is fixed at "medium" for every edge: no HTTP API
// in plan/02-contracts.md exposes a live per-service request-rate bucket
// to the console, and adding one is out of this phase's scope; see
// docs/reports/PHASE_4_REPORT.md, Deviations.

"use client";

import { useMemo } from "react";

import { foldAllIncidents } from "../lib/fold";
import { useVisibleEvents } from "../store/events";

export type NodeStatus = "healthy" | "faulted" | "verified";
export type TrafficLevel = "low" | "medium" | "high";

export interface TopologyNode {
  id: string;
  label: string;
  isTargetService: boolean;
  status: NodeStatus;
  incidentId: string | null;
}

export interface TopologyEdge {
  id: string;
  source: string;
  target: string;
  trafficLevel: TrafficLevel;
  faulted: boolean;
}

export interface TopologyAgentOrb {
  agent: string;
  targetNodeId: string;
}

export interface TopologyState {
  nodes: TopologyNode[];
  edges: TopologyEdge[];
  agents: TopologyAgentOrb[];
}

const NODE_IDS = [
  "target-gateway",
  "target-orders",
  "target-payments",
  "shop-db",
  "redis",
] as const;

const EDGE_DEFS: { id: string; source: string; target: string }[] = [
  { id: "gateway-orders", source: "target-gateway", target: "target-orders" },
  { id: "gateway-payments", source: "target-gateway", target: "target-payments" },
  { id: "orders-shopdb", source: "target-orders", target: "shop-db" },
  { id: "orders-redis", source: "target-orders", target: "redis" },
];

export function useTopologyState(): TopologyState {
  const events = useVisibleEvents();
  return useMemo(() => computeTopology(events), [events]);
}

function computeTopology(events: Parameters<typeof foldAllIncidents>[1]): TopologyState {
  const incidents = foldAllIncidents({}, events);

  const status: Record<string, NodeStatus> = Object.fromEntries(
    NODE_IDS.map((id) => [id, "healthy" as NodeStatus]),
  );
  const owner: Record<string, string | null> = Object.fromEntries(NODE_IDS.map((id) => [id, null]));
  const agents: TopologyAgentOrb[] = [];

  for (const view of Object.values(incidents)) {
    if (view.status === "resolved" || view.status === "escalated") continue;
    for (const service of view.affectedServices) {
      if (!(service in status)) continue;
      status[service] = view.currentPhase === "verify" ? "verified" : "faulted";
      owner[service] = view.id;
      for (const agent of view.activeAgents) {
        if (agents.length < 4) agents.push({ agent, targetNodeId: service });
      }
    }
  }

  const nodes: TopologyNode[] = NODE_IDS.map((id) => ({
    id,
    label: id,
    isTargetService: id.startsWith("target-"),
    status: status[id] ?? "healthy",
    incidentId: owner[id] ?? null,
  }));

  const edges: TopologyEdge[] = EDGE_DEFS.map((e) => ({
    ...e,
    trafficLevel: "medium" as const,
    faulted: status[e.source] === "faulted" || status[e.target] === "faulted",
  }));

  return { nodes, edges, agents };
}
