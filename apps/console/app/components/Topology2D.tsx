"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  Background,
  BackgroundVariant,
  Handle,
  Position,
  ReactFlow,
  type EdgeProps,
  type NodeProps,
  getStraightPath,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Bot, Database, Server } from "lucide-react";

import { useReducedMotion } from "../hooks/useReducedMotion";
import { useTopologyState, type NodeStatus } from "../hooks/useTopologyState";

const STATUS_COLOR: Record<NodeStatus, string> = {
  healthy: "var(--aegis-accent)",
  faulted: "var(--aegis-critical)",
  verified: "var(--aegis-success)",
};

const POSITIONS: Record<string, { x: number; y: number }> = {
  "target-gateway": { x: 260, y: 20 },
  "target-orders": { x: 100, y: 190 },
  "target-payments": { x: 420, y: 190 },
  "shop-db": { x: 20, y: 360 },
  "shop-redis": { x: 240, y: 360 },
};

function AegisNode({ data }: NodeProps) {
  const status = data.status as NodeStatus;
  const isTargetService = data.isTargetService as boolean;
  const reducedMotion = useReducedMotion();
  const prevStatus = useRef(status);
  const [flashing, setFlashing] = useState(false);

  useEffect(() => {
    if (prevStatus.current !== "faulted" && status === "faulted" && !reducedMotion) {
      setFlashing(true);
      const t = setTimeout(() => setFlashing(false), 650);
      prevStatus.current = status;
      return () => clearTimeout(t);
    }
    prevStatus.current = status;
  }, [status, reducedMotion]);

  const color = STATUS_COLOR[status];
  const Icon = isTargetService ? Server : Database;

  return (
    <div
      data-testid="topology-node"
      data-node-id={data.id as string}
      data-status={status}
      className={`flex w-32 flex-col items-center gap-1.5 rounded-lg border-2 px-3 py-2.5 transition-shadow duration-300 ${
        flashing ? "aegis-node-flash" : ""
      }`}
      style={{
        borderColor: color,
        background: "var(--aegis-surface-raised)",
        boxShadow: status !== "healthy" ? `0 0 16px ${color}55` : "none",
      }}
    >
      <Handle type="target" position={Position.Top} style={{ opacity: 0 }} />
      <Icon size={16} style={{ color }} aria-hidden />
      <span className="font-mono-data text-[10px]" style={{ color: "var(--aegis-text)" }}>
        {data.label as string}
      </span>
      <Handle type="source" position={Position.Bottom} style={{ opacity: 0 }} />
      <style>{`
        @keyframes aegis-node-flash {
          0%, 100% { transform: scale(1); }
          30% { transform: scale(1.08); }
        }
        .aegis-node-flash { animation: aegis-node-flash 0.65s ease-out; }
      `}</style>
    </div>
  );
}

function PulseEdge({ sourceX, sourceY, targetX, targetY, data }: EdgeProps) {
  const faulted = data?.faulted as boolean;
  const reducedMotion = useReducedMotion();
  const [path] = getStraightPath({ sourceX, sourceY, targetX, targetY });
  const color = faulted ? "var(--aegis-critical)" : "var(--aegis-border)";

  return (
    <>
      <path d={path} fill="none" stroke={color} strokeWidth={2} />
      {!reducedMotion && (
        <circle r={3} fill={faulted ? "var(--aegis-critical)" : "var(--aegis-accent)"}>
          <animateMotion dur={faulted ? "0.9s" : "1.8s"} repeatCount="indefinite" path={path} />
        </circle>
      )}
    </>
  );
}

const nodeTypes = { aegis: AegisNode };
const edgeTypes = { pulse: PulseEdge };

export function Topology2D() {
  const { nodes: topoNodes, edges: topoEdges, agents } = useTopologyState();
  const containerRef = useRef<HTMLDivElement>(null);
  // Structural, not the full ReactFlowInstance<Node, Edge> generic: onInit
  // hands back an instance typed to this component's own node/edge shape,
  // which doesn't unify with the library's default-generic type. Only
  // fitView is ever called on it, so that's all this ref needs to know.
  const flowRef = useRef<{
    fitView: (opts?: { padding?: number; duration?: number }) => void;
  } | null>(null);

  // Detail panel opening/closing resizes this container; React Flow's
  // fitView only runs once on mount, so without this the topology drifts
  // out of the visible area whenever the panel toggles (found live: the
  // right-side nodes clipped off-screen once the panel opened).
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const observer = new ResizeObserver(() => {
      flowRef.current?.fitView({ padding: 0.3, duration: 200 });
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const nodes = useMemo(
    () =>
      topoNodes.map((n) => ({
        id: n.id,
        type: "aegis",
        position: POSITIONS[n.id] ?? { x: 0, y: 0 },
        data: { ...n },
        draggable: false,
        selectable: false,
      })),
    [topoNodes],
  );

  const edges = useMemo(
    () =>
      topoEdges.map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        type: "pulse",
        data: { faulted: e.faulted },
      })),
    [topoEdges],
  );

  return (
    <div ref={containerRef} className="relative h-full w-full" data-testid="topology-2d">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        fitView
        fitViewOptions={{ padding: 0.3 }}
        onInit={(instance) => {
          flowRef.current = instance;
        }}
        proOptions={{ hideAttribution: true }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        panOnDrag={false}
        zoomOnScroll={false}
        zoomOnPinch={false}
        zoomOnDoubleClick={false}
      >
        <Background
          variant={BackgroundVariant.Dots}
          color="var(--aegis-border)"
          gap={24}
          size={1}
        />
      </ReactFlow>
      {agents.length > 0 && (
        <div
          className="pointer-events-none absolute bottom-2 left-2 flex items-center gap-1 font-mono-data text-[10px]"
          style={{ color: "var(--aegis-text-secondary)" }}
        >
          <Bot size={11} aria-hidden />
          {agents.map((a) => a.agent).join(", ")} working
        </div>
      )}
    </div>
  );
}
