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
  onReconnect?: () => void;
}

function connect<In, Out>(path: string, h: Handlers<Out>): Connection<In> {
  let ws: WebSocket;
  let closed = false;
  let retry: ReturnType<typeof setTimeout> | undefined;
  let connectedOnce = false;
  const queue: In[] = [];
  const binaryQueue: ArrayBuffer[] = [];
  let binaryQueueBytes = 0;
  const maxQueuedAudioBytes = 64 * 1024; // keep at most 2 s of 16 kHz mono PCM while connecting
  function open() {
    ws = new WebSocket(`${WS_URL}${path}`);
    ws.binaryType = "arraybuffer";
    ws.onopen = () => {
      if (connectedOnce) h.onReconnect?.();
      connectedOnce = true;
      queue.splice(0).forEach((e) => ws.send(JSON.stringify(e)));
      while (binaryQueue.length) {
        const chunk = binaryQueue.shift()!;
        binaryQueueBytes -= chunk.byteLength;
        ws.send(chunk);
      }
    };
    ws.onmessage = (msg) => {
      if (typeof msg.data === "string") h.onEvent(JSON.parse(msg.data) as Out);
      else h.onBinary?.(msg.data as ArrayBuffer);
    };
    ws.onclose = (event) => {
      binaryQueue.length = 0;
      binaryQueueBytes = 0;
      h.onClose?.();
      if (!closed && event.code !== 4404) retry = setTimeout(open, 1000);
    };
  }
  open();
  return {
    send: (e) => (ws.readyState === WebSocket.OPEN ? ws.send(JSON.stringify(e)) : queue.push(e)),
    sendBinary: (chunk) => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(chunk);
      } else if (ws.readyState === WebSocket.CONNECTING) {
        binaryQueue.push(chunk);
        binaryQueueBytes += chunk.byteLength;
        while (binaryQueueBytes > maxQueuedAudioBytes && binaryQueue.length) {
          binaryQueueBytes -= binaryQueue.shift()!.byteLength;
        }
      }
    },
    close: () => { closed = true; clearTimeout(retry); ws.close(); },
  };
}

export function connectCustomer(
  sessionId: string,
  onEvent: (e: CustomerOutbound) => void,
  options: { onBinary?: (chunk: ArrayBuffer) => void; onClose?: () => void; onReconnect?: () => void } = {},
): Connection<CustomerInbound> {
  if (USE_MOCKS) return mockBackend().connectCustomer(sessionId, onEvent);
  return connect<CustomerInbound, CustomerOutbound>(`/ws/sessions/${sessionId}`, { onEvent, ...options });
}

export function connectMerchant(onEvent: (e: MerchantOutbound) => void, merchantId?: string | null): Connection<never> {
  if (USE_MOCKS) return { send: () => {}, close: mockBackend().subscribeMerchant(onEvent) };
  return connect<never, MerchantOutbound>(merchantId ? `/ws/merchant?merchant_id=${encodeURIComponent(merchantId)}` : "/ws/merchant", { onEvent });
}
