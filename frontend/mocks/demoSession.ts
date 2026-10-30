// Scripted events for USE_MOCKS mode: one short demo session. Shapes must match lib/types.ts.
import type { CustomerOutbound, MerchantOutbound } from "@/lib/types";

export const MOCK_SESSION_ID = "00000000-0000-4000-8000-000000000001";
const now = () => new Date().toISOString();

export const mockCustomerSession: { delayMs: number; event: CustomerOutbound }[] = [
  { delayMs: 0, event: { type: "state", state: "intro", message: null } },
  { delayMs: 0, event: { type: "agent_state", state: "speaking" } },
  {
    delayMs: 300,
    event: { type: "transcript", speaker: "hermion", text: "Namaskaram! I'm Hermion from Lakshmi Fashions.", final: true },
  },
  { delayMs: 600, event: { type: "agent_state", state: "idle" } },
];

export function mockCustomerReply(text: string): { delayMs: number; event: CustomerOutbound }[] {
  return [
    { delayMs: 0, event: { type: "transcript", speaker: "customer", text, final: true } },
    { delayMs: 50, event: { type: "agent_state", state: "thinking" } },
    { delayMs: 600, event: { type: "transcript", speaker: "hermion", text: `(mock) You said: ${text}`, final: true } },
    { delayMs: 650, event: { type: "agent_state", state: "idle" } },
  ];
}

export const mockMerchantStream: { delayMs: number; event: MerchantOutbound }[] = [
  {
    delayMs: 200,
    event: {
      type: "session_created",
      session: { session_id: MOCK_SESSION_ID, state: "intro", language: "te", started_at: now(), ended_at: null },
    },
  },
  {
    delayMs: 500,
    event: {
      type: "trace",
      session_id: MOCK_SESSION_ID,
      kind: "message",
      data: { speaker: "hermion", text: "Namaskaram! I'm Hermion from Lakshmi Fashions.", channel: "customer" },
    },
  },
];
