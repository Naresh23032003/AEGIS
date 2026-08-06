"use client";

import { useEffect } from "react";

import { useEventStore } from "../store/events";

/** Opens the one WebSocket connection for the whole app. Mounted once in
 * the root layout; every other component only ever selects from the
 * store (plan/05-frontend.md: "The store is the only WS consumer"). */
export function LiveConnection() {
  const connect = useEventStore((s) => s.connect);
  const disconnect = useEventStore((s) => s.disconnect);

  useEffect(() => {
    connect();
    return () => disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return null;
}
