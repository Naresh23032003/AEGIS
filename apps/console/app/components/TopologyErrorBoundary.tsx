"use client";

import { Component, type ReactNode } from "react";

interface Props {
  fallback: ReactNode;
  children: ReactNode;
  onError?: () => void;
}

interface State {
  failed: boolean;
}

/** Last-resort guard around the R3F scene: if Canvas construction throws
 * for a reason feature-detection missed (a driver quirk, a context
 * creation race), render the React Flow fallback instead of a blank or
 * broken screen. plan/05-frontend.md, Topology scene (R3F), Fallback:
 * "no error flash." */
export class TopologyErrorBoundary extends Component<Props, State> {
  state: State = { failed: false };

  static getDerivedStateFromError(): State {
    return { failed: true };
  }

  componentDidCatch() {
    this.props.onError?.();
  }

  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}
