"use client";

// R3F topology scene, plan/05-frontend.md "Topology scene (R3F)". Reads
// only useTopologyState() -- the same hook Topology2D consumes -- so the
// two renderers can never drift (plan/05, Fallback: "Both consume one
// useTopologyState() hook"). Only ever mounted client-side, see
// TopologyRenderer.tsx: no SSR pass, no hydration-mismatch risk, and
// useLayoutEffect below is safe.
//
// Status colors are the design-system/MASTER.md token hexes, hand-copied:
// three.js materials take real colors, not CSS custom properties, and
// there is no useful way to hand a `var(--aegis-accent)` string to a
// MeshStandardMaterial. The drei <Html> labels, by contrast, are real DOM
// and use the CSS vars directly like every other screen.

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Grid, Html, Line } from "@react-three/drei";
import { Bloom, EffectComposer } from "@react-three/postprocessing";
import * as THREE from "three";
import { RoundedBoxGeometry, type Line2 } from "three-stdlib";
import { Bot, Database, Server } from "lucide-react";

import { useReducedMotion } from "../hooks/useReducedMotion";
import {
  useTopologyState,
  type NodeStatus,
  type TopologyAgentOrb,
  type TopologyEdge,
  type TopologyNode,
  type TrafficLevel,
} from "../hooks/useTopologyState";
import { FpsMeter } from "./FpsMeter";

const NODE_IDS = [
  "target-gateway",
  "target-orders",
  "target-payments",
  "shop-db",
  "redis",
] as const;

const NODE_POSITIONS: Record<string, [number, number, number]> = {
  "target-gateway": [0, 0, -4],
  "target-orders": [-3.2, 0, -0.5],
  "target-payments": [3.2, 0, -0.5],
  "shop-db": [-3.2, 0, 3.2],
  redis: [1.2, 0, 3.2],
};

const CORE_POSITION: [number, number, number] = [0, 3.4, 0];

const NODE_COLOR: Record<NodeStatus, string> = {
  healthy: "#1c7c8c",
  faulted: "#F43F5E",
  verified: "#34D399",
};

const EDGE_COLOR = { calm: "#22D3EE", faulted: "#F43F5E" };

const TRAFFIC_SPEED: Record<TrafficLevel, number> = { low: 0.35, medium: 0.7, high: 1.3 };

const REST_CAMERA_POSITION = new THREE.Vector3(0, 6.5, 9.5);
const REST_CAMERA_TARGET = new THREE.Vector3(0, 0.6, 0);

const NODE_SIZE: [number, number, number] = [1.15, 0.7, 1.15];
const NODE_Y = 0.38;
const FLASH_MS = 650;

interface Topology3DProps {
  /** Called once if Canvas construction itself throws; TopologyRenderer
   * treats it the same as a failed feature-detection and swaps to the
   * React Flow fallback. */
  onFailure: () => void;
}

export function Topology3D({ onFailure }: Topology3DProps) {
  const { nodes, edges, agents } = useTopologyState();
  // TopologyRenderer routes a reduced-motion user to the 2D fallback, so
  // this is only ever true when they overrode it with ?view=3d. plan/05,
  // Fallback: "the scene mounts but renders static: no idle ticker, no
  // ambient pulse, frames render only on state changes." Before this the
  // forced scene animated exactly like the unforced one (defect 6,
  // docs/reports/FINAL_VERIFICATION.md), which the preference forbids
  // whatever route the user took to get here.
  const reducedMotion = useReducedMotion();
  const [tabHidden, setTabHidden] = useState(false);
  const [showPerf, setShowPerf] = useState(false);
  const [fps, setFps] = useState<number | null>(null);

  useEffect(() => {
    const onVisibility = () => setTabHidden(document.hidden);
    onVisibility();
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, []);

  useEffect(() => {
    setShowPerf(new URLSearchParams(window.location.search).get("perf") === "1");
  }, []);

  const hasActiveIncident = useMemo(
    () => nodes.some((n) => n.status !== "healthy") || agents.length > 0,
    [nodes, agents],
  );

  // plan/05: bloom, DPR cap 1.5, demand frameloop when idle, invalidate on
  // events, full pause on hidden tab. "always" (a real 60fps loop) only
  // runs while an incident is animating something (node flash, orb
  // choreography, camera ease); otherwise "demand" plus a slow 5fps
  // invalidate ticker (IdleTicker, below) keeps the ambient traffic pulse
  // visibly flowing without paying for a continuous 60fps idle render.
  // Reduced motion collapses both cases to "demand" with no ticker, so a
  // frame is only ever drawn when the topology state actually changed.
  const frameloop: "never" | "always" | "demand" = tabHidden
    ? "never"
    : hasActiveIncident && !reducedMotion
      ? "always"
      : "demand";

  return (
    <div className="relative h-full w-full" data-testid="topology-3d">
      <Canvas
        dpr={[1, 1.5]}
        frameloop={frameloop}
        camera={{
          position: [REST_CAMERA_POSITION.x, REST_CAMERA_POSITION.y, REST_CAMERA_POSITION.z],
          fov: 42,
        }}
        gl={{ antialias: true, powerPreference: "high-performance" }}
        onCreated={({ gl }) => {
          gl.domElement.addEventListener("webglcontextlost", (e) => {
            e.preventDefault();
            onFailure();
          });
        }}
      >
        <color attach="background" args={["#050607"]} />
        <ambientLight intensity={0.55} />
        <directionalLight position={[4, 8, 3]} intensity={0.6} />

        <Grid
          position={[0, -0.01, 0]}
          args={[26, 26]}
          cellSize={1}
          cellThickness={0.5}
          cellColor="#1E242C"
          sectionSize={4}
          sectionThickness={1}
          sectionColor="#1E242C"
          fadeDistance={20}
          fadeStrength={1.2}
        />

        <TopologyNodes nodes={nodes} still={reducedMotion} />
        <TopologyEdges edges={edges} still={reducedMotion} />
        <TopologyLabels nodes={nodes} />
        {agents.map((orb, i) => (
          <AgentOrb key={orb.agent} orb={orb} index={i} still={reducedMotion} />
        ))}
        <CoreMarker />

        <FaultCamera nodes={nodes} still={reducedMotion} />
        <IdleTicker idle={frameloop === "demand" && !reducedMotion} />
        {showPerf && <FpsMeter onSample={setFps} />}

        <EffectComposer multisampling={0}>
          <Bloom intensity={0.55} luminanceThreshold={0.35} luminanceSmoothing={0.85} mipmapBlur />
        </EffectComposer>
      </Canvas>

      {agents.length > 0 && (
        <div
          className="pointer-events-none absolute bottom-2 left-2 flex items-center gap-1 font-mono-data text-[10px]"
          style={{ color: "var(--aegis-text-secondary)" }}
        >
          <Bot size={11} aria-hidden />
          {agents.map((a) => a.agent).join(", ")} working
        </div>
      )}
      {showPerf && (
        <div
          data-testid="fps-meter"
          className="pointer-events-none absolute right-2 top-2 rounded border px-2 py-1 font-mono-data text-[10px]"
          style={{
            borderColor: "var(--aegis-border)",
            background: "var(--aegis-surface-raised)",
            color: "var(--aegis-text)",
          }}
        >
          {fps === null ? "fps: --" : `fps: ${fps}`}
        </div>
      )}
    </div>
  );
}

/** One instancedMesh, one material, five per-instance colors -- per the
 * phase brief's gotcha: "Instanced meshes plus per-node emissive color
 * needs per-instance color attributes; do not create one material per
 * node." Emissive glow is faked with an unlit, bright, saturated
 * instanceColor plus Bloom's luminance threshold rather than true
 * per-instance emissive (three's InstancedMesh only wires instanceColor
 * into the base color channel, not emissive; a real per-instance emissive
 * would need a hand-patched shader for five boxes, not worth the
 * complexity here). */
function TopologyNodes({ nodes, still }: { nodes: TopologyNode[]; still: boolean }) {
  const meshRef = useRef<THREE.InstancedMesh>(null);
  const geometry = useMemo(() => new RoundedBoxGeometry(...NODE_SIZE, 2, 0.12), []);
  const material = useMemo(
    () => new THREE.MeshStandardMaterial({ toneMapped: false, roughness: 0.4, metalness: 0.05 }),
    [],
  );
  const prevStatus = useRef<Record<string, NodeStatus>>({});
  const flashUntil = useRef<Record<string, number>>({});

  const tmpColor = useMemo(() => new THREE.Color(), []);
  const tmpMatrix = useMemo(() => new THREE.Matrix4(), []);
  const tmpPos = useMemo(() => new THREE.Vector3(), []);
  const tmpQuat = useMemo(() => new THREE.Quaternion(), []);
  const tmpScale = useMemo(() => new THREE.Vector3(1, 1, 1), []);

  useLayoutEffect(() => {
    const mesh = meshRef.current;
    if (!mesh) return;
    nodes.forEach((node, i) => {
      if (
        !still &&
        prevStatus.current[node.id] &&
        prevStatus.current[node.id] !== "faulted" &&
        node.status === "faulted"
      ) {
        flashUntil.current[node.id] = performance.now() + FLASH_MS;
      }
      prevStatus.current[node.id] = node.status;

      tmpColor.set(NODE_COLOR[node.status]);
      mesh.setColorAt(i, tmpColor);
    });
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
  }, [nodes, still, tmpColor]);

  useFrame(() => {
    const mesh = meshRef.current;
    if (!mesh) return;
    const now = performance.now();
    nodes.forEach((node, i) => {
      const pos = NODE_POSITIONS[node.id] ?? [0, 0, 0];
      let scale = 1;
      const until = flashUntil.current[node.id];
      if (until) {
        const remaining = until - now;
        if (remaining > 0) {
          scale = 1 + Math.sin((1 - remaining / FLASH_MS) * Math.PI) * 0.12;
        } else {
          delete flashUntil.current[node.id];
        }
      }
      tmpPos.set(pos[0], NODE_Y, pos[2]);
      tmpScale.set(scale, scale, scale);
      tmpMatrix.compose(tmpPos, tmpQuat, tmpScale);
      mesh.setMatrixAt(i, tmpMatrix);
    });
    mesh.instanceMatrix.needsUpdate = true;
  });

  return (
    <instancedMesh
      ref={meshRef}
      args={[geometry, material, NODE_IDS.length]}
      castShadow={false}
      receiveShadow={false}
    />
  );
}

function TopologyLabels({ nodes }: { nodes: TopologyNode[] }) {
  return (
    <>
      {nodes.map((node) => {
        const pos = NODE_POSITIONS[node.id] ?? [0, 0, 0];
        const Icon = node.isTargetService ? Server : Database;
        return (
          <Html
            key={node.id}
            position={[pos[0], NODE_Y + 0.75, pos[2]]}
            center
            occlude={false}
            distanceFactor={9}
          >
            <div
              className="flex select-none flex-col items-center gap-1"
              data-testid="topology-node-3d"
              data-node-id={node.id}
              data-status={node.status}
            >
              <Icon size={14} style={{ color: NODE_COLOR[node.status] }} aria-hidden />
              <span
                className="font-mono-data text-[10px] whitespace-nowrap"
                style={{ color: "var(--aegis-text)" }}
              >
                {node.label}
              </span>
            </div>
          </Html>
        );
      })}
    </>
  );
}

function TopologyEdges({ edges, still }: { edges: TopologyEdge[]; still: boolean }) {
  return (
    <>
      {edges.map((edge) => (
        <PulseEdge key={edge.id} edge={edge} still={still} />
      ))}
    </>
  );
}

function PulseEdge({ edge, still }: { edge: TopologyEdge; still: boolean }) {
  const points = useMemo<[number, number, number][]>(() => {
    const from = NODE_POSITIONS[edge.source] ?? [0, 0, 0];
    const to = NODE_POSITIONS[edge.target] ?? [0, 0, 0];
    return [
      [from[0], NODE_Y, from[2]],
      [to[0], NODE_Y, to[2]],
    ];
  }, [edge.source, edge.target]);
  const lineRef = useRef<Line2>(null);
  const speed = TRAFFIC_SPEED[edge.trafficLevel] * (edge.faulted ? 2.2 : 1);

  useFrame((_, delta) => {
    // The dashes are the ambient traffic pulse. Under reduced motion they
    // keep their starting offset, so a state-change repaint redraws the
    // same line rather than advancing it.
    if (still) return;
    const material = lineRef.current?.material;
    if (!material) return;
    material.dashOffset -= delta * speed;
  });

  return (
    <Line
      ref={lineRef}
      points={points}
      color={edge.faulted ? EDGE_COLOR.faulted : EDGE_COLOR.calm}
      lineWidth={edge.faulted ? 2.2 : 1.3}
      dashed
      dashSize={0.35}
      gapSize={0.28}
      transparent
      opacity={edge.faulted ? 0.95 : 0.5}
    />
  );
}

const ORB_GEOMETRY = new THREE.SphereGeometry(0.15, 16, 16);
const ORB_MATERIAL = new THREE.MeshStandardMaterial({ color: "#22D3EE", toneMapped: false });
const ORB_TMP = new THREE.Vector3();

/** Cosmetic choreography, not simulation, per the phase brief: position is
 * derived every frame from elapsed time and the orb's slot index, lerped
 * toward an orbit point around the target node. Keyed by agent name in
 * the parent map, so a genuinely new agent starts fresh at the AEGIS core
 * and glides out; the same agent staying active across renders keeps its
 * orbit uninterrupted. */
function AgentOrb({ orb, index, still }: { orb: TopologyAgentOrb; index: number; still: boolean }) {
  const target = NODE_POSITIONS[orb.targetNodeId] ?? [0, 0, 0];
  const ref = useRef<THREE.Mesh>(null);
  const current = useRef(new THREE.Vector3(...CORE_POSITION));

  useFrame((state, delta) => {
    const mesh = ref.current;
    if (!mesh) return;
    // Reduced motion drops the clock term: the orb still says which node
    // the agent is working on, it just parks at one point on the orbit
    // instead of circling it.
    const t = still ? index * 1.9 : state.clock.elapsedTime * 1.4 + index * 1.9;
    const radius = 0.85;
    ORB_TMP.set(
      target[0] + Math.cos(t) * radius,
      NODE_Y + 0.55 + Math.sin(t * 1.6) * 0.07,
      target[2] + Math.sin(t) * radius,
    );
    if (still) {
      current.current.copy(ORB_TMP);
    } else {
      current.current.lerp(ORB_TMP, 1 - Math.pow(0.0025, delta));
    }
    mesh.position.copy(current.current);
  });

  return (
    <mesh ref={ref} geometry={ORB_GEOMETRY} material={ORB_MATERIAL} position={CORE_POSITION} />
  );
}

function CoreMarker() {
  return (
    <mesh position={CORE_POSITION}>
      <octahedronGeometry args={[0.14, 0]} />
      <meshStandardMaterial color="#22D3EE" toneMapped={false} transparent opacity={0.5} />
    </mesh>
  );
}

/** One gentle camera ease-in toward the fault, then it holds -- plan/05:
 * "no wild camera moves; one gentle move per incident." `still` cuts the
 * ease: the camera jumps to the same resting place in a single frame, so
 * a reduced-motion viewer sees the fault framed without the move. */
function FaultCamera({ nodes, still }: { nodes: TopologyNode[]; still: boolean }) {
  const { camera } = useThree();
  const lookAt = useRef(REST_CAMERA_TARGET.clone());
  const desiredPos = useMemo(() => new THREE.Vector3(), []);
  const desiredTarget = useMemo(() => new THREE.Vector3(), []);

  useFrame((_, delta) => {
    const faulted = nodes.find((n) => n.status === "faulted");
    if (faulted) {
      const pos = NODE_POSITIONS[faulted.id] ?? [0, 0, 0];
      desiredTarget.set(pos[0], NODE_Y, pos[2]);
      desiredPos.set(pos[0] * 0.6, 4.2, pos[2] + 5.5);
    } else {
      desiredTarget.copy(REST_CAMERA_TARGET);
      desiredPos.copy(REST_CAMERA_POSITION);
    }
    if (still) {
      camera.position.copy(desiredPos);
      lookAt.current.copy(desiredTarget);
    } else {
      const alpha = 1 - Math.pow(0.001, delta);
      camera.position.lerp(desiredPos, alpha);
      lookAt.current.lerp(desiredTarget, alpha);
    }
    camera.lookAt(lookAt.current);
  });

  return null;
}

/** frameloop="demand" stops rendering once nothing is invalidating it. The
 * ambient traffic pulse on healthy edges is meant to keep flowing at all
 * times (plan/05: edges show a "slow animated pulse traveling in the
 * traffic direction" independent of incidents), so idle mode nudges a
 * repaint at 5fps instead of 60fps -- visibly alive, a twelfth of the
 * idle render cost. Under reduced motion the caller passes idle=false and
 * this never starts, which is what makes the forced scene hold still. */
function IdleTicker({ idle }: { idle: boolean }) {
  const invalidate = useThree((s) => s.invalidate);
  useEffect(() => {
    if (!idle) return;
    const id = setInterval(invalidate, 200);
    return () => clearInterval(id);
  }, [idle, invalidate]);
  return null;
}
