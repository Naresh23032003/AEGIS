// Feature-detects WebGL exactly the way the 3D scene will need it, used
// once by TopologyRenderer to decide between the R3F scene and the React
// Flow fallback (plan/05-frontend.md, Topology scene (R3F), Fallback: "on
// WebGL context failure ... render the React Flow version"). Never throws:
// browsers with WebGL disabled by policy throw from getContext rather than
// returning null, so both paths are handled the same way.
export function hasWebGL(): boolean {
  if (typeof window === "undefined" || typeof document === "undefined") return false;
  try {
    const canvas = document.createElement("canvas");
    const gl =
      canvas.getContext("webgl2") ||
      canvas.getContext("webgl") ||
      canvas.getContext("experimental-webgl");
    return !!gl;
  } catch {
    return false;
  }
}
