// Reconnecting WebSocket client for /ws/events. plan/02-contracts.md,
// WebSocket: server tails the Redis stream and forwards EventEnvelope
// JSON text frames, plus a {"type":"ping"} heartbeat every 20s. plan/05:
// "One WebSocket connection (reconnecting, exponential backoff) feeding a
// Zustand store; all components select from the store." This is the only
// module in the console that opens a socket.

import type { EventEnvelope } from "./types";

export type WsStatus = "connecting" | "open" | "reconnecting" | "closed";

const MIN_BACKOFF_MS = 500;
const MAX_BACKOFF_MS = 15_000;

function isEventEnvelope(msg: unknown): msg is EventEnvelope {
  return (
    typeof msg === "object" &&
    msg !== null &&
    "incident_id" in msg &&
    "type" in msg &&
    "payload" in msg
  );
}

export class EventSocket {
  private url: string;
  private replayIncidentId: string | null;
  private socket: WebSocket | null = null;
  private attempt = 0;
  private closedByUser = false;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  onEvent: (envelope: EventEnvelope) => void = () => {};
  onStatus: (status: WsStatus) => void = () => {};

  constructor(url: string, opts?: { replayIncidentId?: string }) {
    this.url = url;
    this.replayIncidentId = opts?.replayIncidentId ?? null;
  }

  connect(): void {
    this.closedByUser = false;
    this.open();
  }

  private open(): void {
    if (typeof WebSocket === "undefined") return;
    this.onStatus(this.attempt === 0 ? "connecting" : "reconnecting");
    const socket = new WebSocket(this.url);
    this.socket = socket;

    socket.onopen = () => {
      this.attempt = 0;
      if (this.replayIncidentId) {
        socket.send(JSON.stringify({ replay_incident: this.replayIncidentId }));
      }
      this.onStatus("open");
    };

    socket.onmessage = (ev: MessageEvent<string>) => {
      let msg: unknown;
      try {
        msg = JSON.parse(ev.data);
      } catch {
        return;
      }
      if (isEventEnvelope(msg)) {
        this.onEvent(msg);
      }
      // {"type": "ping"} heartbeat frames carry no incident_id/payload and
      // are intentionally dropped here.
    };

    socket.onclose = () => {
      this.socket = null;
      if (this.closedByUser) {
        this.onStatus("closed");
        return;
      }
      this.scheduleReconnect();
    };

    socket.onerror = () => {
      socket.close();
    };
  }

  private scheduleReconnect(): void {
    this.onStatus("reconnecting");
    const backoff = Math.min(MAX_BACKOFF_MS, MIN_BACKOFF_MS * 2 ** this.attempt);
    const jitter = backoff * (0.5 + Math.random() * 0.5);
    this.attempt += 1;
    this.reconnectTimer = setTimeout(() => this.open(), jitter);
  }

  close(): void {
    this.closedByUser = true;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.socket?.close();
    this.socket = null;
  }
}
