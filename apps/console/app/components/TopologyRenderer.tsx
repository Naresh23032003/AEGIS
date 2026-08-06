"use client";

// Picks the topology renderer per plan/05-frontend.md, Topology scene
// (R3F), Fallback: "on WebGL context failure, or ?view=2d, or reduced
// motion, render the React Flow version ... first-class build target ...
// no error flash." plan/06 phase 5: "the R3F topology replaces React Flow
// as the default renderer."
//
// Starts on the 2D renderer unconditionally -- the same output on the
// server and on the client's first paint, so there is nothing to
// hydration-mismatch on. A client-only effect then resolves the real
// decision (WebGL support, reduced motion, ?view= override) and swaps to
// 3D if it wins; Topology3D itself loads via next/dynamic(ssr:false), so
// it never takes part in server rendering at all. TopologyErrorBoundary
// covers the remaining case feature-detection can't: a WebGL context that
// reports available but then fails during Canvas construction.

import { useCallback, useEffect, useState } from "react";
import dynamic from "next/dynamic";

import { useReducedMotion } from "../hooks/useReducedMotion";
import { hasWebGL } from "../lib/webgl";
import { readViewParam, VIEW_CHANGED_EVENT, type ViewParam } from "../lib/viewParam";
import { Topology2D } from "./Topology2D";
import { TopologyErrorBoundary } from "./TopologyErrorBoundary";

const Topology3D = dynamic(() => import("./Topology3D").then((m) => m.Topology3D), {
  ssr: false,
});

export function TopologyRenderer() {
  const reducedMotion = useReducedMotion();
  const [viewParam, setViewParam] = useState<ViewParam>(null);
  const [webglOk, setWebglOk] = useState(false);
  const [checked, setChecked] = useState(false);
  const [erroredOut, setErroredOut] = useState(false);

  useEffect(() => {
    setViewParam(readViewParam());
    setWebglOk(hasWebGL());
    setChecked(true);
    const onChange = () => setViewParam(readViewParam());
    window.addEventListener(VIEW_CHANGED_EVENT, onChange);
    window.addEventListener("popstate", onChange);
    return () => {
      window.removeEventListener(VIEW_CHANGED_EVENT, onChange);
      window.removeEventListener("popstate", onChange);
    };
  }, []);

  const onWebglFailure = useCallback(() => setErroredOut(true), []);

  const use3D =
    checked &&
    !erroredOut &&
    (viewParam === "3d" ? true : viewParam === "2d" ? false : !reducedMotion && webglOk);

  if (!use3D) return <Topology2D />;

  return (
    <TopologyErrorBoundary fallback={<Topology2D />} onError={onWebglFailure}>
      <Topology3D onFailure={onWebglFailure} />
    </TopologyErrorBoundary>
  );
}
