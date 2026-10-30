// WebSocket clients for both panes (docs/api.md). With NEXT_PUBLIC_USE_MOCKS=true they connect to
// mocks/backend.ts instead of a socket, so UI lanes can work without a backend.
import { mockBackend } from "@/mocks/backend";
import { USE_MOCKS, WS_URL } from "./config";
import type { CustomerInbound, CustomerOutbound, MerchantOutbound } from "./types";

export interface Connection<In> {
  send: (event: In) => void;
  sendBinary?: (chunk: ArrayBuffer) => void;
  close: () => void;
}

interface Handlers<Out> {
  onEvent: (e: Out) => void;
  onBinary?: (chunk: ArrayBuffer) => void;
  onClose?: () => void;
}

function connect<In, Out>(path: string, h: Handlers<Out>): Connection<In> {
  const ws = new WebSocket(`${WS_URL}${path}`);
  ws.binaryType = "arraybuffer";
  const queue: In[] = [];
  ws.onopen = () => queue.splice(0).forEach((e) => ws.send(JSON.stringify(e)));
  ws.onmessage = (msg) => {
    if (typeof msg.data === "string") h.onEvent(JSON.parse(msg.data) as Out);
    else h.onBinary?.(msg.data as ArrayBuffer);
  };
  ws.onclose = () => h.onClose?.();
  return {
    send: (e) => (ws.readyState === WebSocket.OPEN ? ws.send(JSON.stringify(e)) : queue.push(e)),
    sendBinary: (chunk) => ws.readyState === WebSocket.OPEN && ws.send(chunk),
    close: () => ws.close(),
  };
}

export function connectCustomer(
  sessionId: string,
  onEvent: (e: CustomerOutbound) => void,
  options: { onBinary?: (chunk: ArrayBuffer) => void; onClose?: () => void } = {},
): Connection<CustomerInbound> {
  if (USE_MOCKS) return mockBackend().connectCustomer(sessionId, onEvent);
  return connect<CustomerInbound, CustomerOutbound>(`/ws/sessions/${sessionId}`, { onEvent, ...options });
}

export function connectMerchant(onEvent: (e: MerchantOutbound) => void): Connection<never> {
  if (USE_MOCKS) return { send: () => {}, close: mockBackend().subscribeMerchant(onEvent) };
  return connect<never, MerchantOutbound>("/ws/merchant", { onEvent });
}
