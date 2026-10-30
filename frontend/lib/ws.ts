// WebSocket clients for both panes (docs/api.md). With NEXT_PUBLIC_USE_MOCKS=true they replay
// frontend/mocks instead of connecting, so UI lanes can work without a backend.
import { USE_MOCKS, WS_URL } from "./config";
import { mockCustomerReply, mockCustomerSession, mockMerchantStream } from "@/mocks/demoSession";
import type { CustomerInbound, CustomerOutbound, MerchantOutbound } from "./types";

export interface Connection<In> {
  send: (event: In) => void;
  close: () => void;
}

function connect<In, Out>(path: string, onEvent: (e: Out) => void, onClose?: () => void): Connection<In> {
  const ws = new WebSocket(`${WS_URL}${path}`);
  const queue: In[] = [];
  ws.onopen = () => queue.splice(0).forEach((e) => ws.send(JSON.stringify(e)));
  ws.onmessage = (msg) => {
    if (typeof msg.data === "string") onEvent(JSON.parse(msg.data) as Out);
  };
  ws.onclose = () => onClose?.();
  return {
    send: (e) => (ws.readyState === WebSocket.OPEN ? ws.send(JSON.stringify(e)) : queue.push(e)),
    close: () => ws.close(),
  };
}

function replay<T>(events: { delayMs: number; event: T }[], onEvent: (e: T) => void): () => void {
  const timers = events.map(({ delayMs, event }) => setTimeout(() => onEvent(event), delayMs));
  return () => timers.forEach(clearTimeout);
}

export function connectCustomer(
  sessionId: string,
  onEvent: (e: CustomerOutbound) => void,
  onClose?: () => void,
): Connection<CustomerInbound> {
  if (USE_MOCKS) {
    const stops = [replay(mockCustomerSession, onEvent)];
    return {
      send: (e) => {
        if (e.type === "text_input") stops.push(replay(mockCustomerReply(e.text), onEvent));
      },
      close: () => stops.forEach((s) => s()),
    };
  }
  return connect<CustomerInbound, CustomerOutbound>(`/ws/sessions/${sessionId}`, onEvent, onClose);
}

export function connectMerchant(onEvent: (e: MerchantOutbound) => void): Connection<never> {
  if (USE_MOCKS) {
    const stop = replay(mockMerchantStream, onEvent);
    return { send: () => {}, close: stop };
  }
  return connect<never, MerchantOutbound>("/ws/merchant", onEvent);
}
