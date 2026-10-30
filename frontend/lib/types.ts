// Mirrors backend/app/schemas/{common,public,merchant,events}.py. Keep in sync (docs/api.md).
// Money is a decimal string on the wire, e.g. "850.00".

export type Money = string;

export type SessionState =
  | "intro"
  | "discovery"
  | "negotiating"
  | "pending_merchant"
  | "briefing"
  | "in_person"
  | "accepted"
  | "declined"
  | "exited";

export const TERMINAL_STATES: readonly SessionState[] = ["accepted", "declined", "exited"];

export type AgentState = "idle" | "listening" | "thinking" | "speaking" | "happy" | "negotiating";

export interface ApiErrorBody {
  error: { code: string; message: string };
}

// ---- customer REST (public: never contains private fields) ----
export interface SessionCreate { qr_token: string; device_id: string }
export interface SessionCreated { session_id: string }
export interface BasketLinePublic { product_id: string; product_name: string; qty: number; line_total: Money }
export interface BasketPublic { lines: BasketLinePublic[]; total: Money }
export interface ConfirmResponse { state: SessionState; basket: BasketPublic }
export interface ExitResponse { state: SessionState }

// ---- merchant REST ----
export interface MerchantProfile {
  merchant_id: string;
  shop_name: string;
  shop_description: string;
  languages: string[];
  negotiation_instructions: string;
  bundle_allowed: boolean;
  qr_token: string;
}
export interface Product {
  product_id: string;
  merchant_id: string;
  product_name: string;
  category: string;
  attributes: Record<string, unknown>;
  aliases: string[];
  listed_price: Money;
  target_price: Money | null;
  minimum_price: Money;
  unit_cost: Money;
  available_stock: number;
  negotiable: boolean;
}
export type GoalType = "clear_stock" | "preserve_stock" | "bigger_baskets";
export interface Goal { goal_id: string; goal_type: GoalType; product_ids: string[]; instructions: string }
export interface SessionSummary {
  session_id: string;
  state: SessionState;
  language: string | null;
  started_at: string;
  ended_at: string | null;
}
export interface TraceMessage {
  id: string;
  channel: "customer" | "briefing";
  speaker: "customer" | "hermion" | "merchant";
  text: string;
  language: string | null;
  text_translated: string | null;
  created_at: string;
}
export interface MerchantBasketLine {
  product_id: string;
  product_name: string;
  qty: number;
  listed_price: Money;
  line_total: Money;
  contribution: Money;
  below_minimum: boolean;
}
export interface MerchantBasket { lines: MerchantBasketLine[]; total: Money; contribution: Money }
export type ReviewAction = "accept" | "decline" | "renegotiate_hermion" | "renegotiate_in_person";

export interface HealthCheck { status: "ok" | "fake" | "error"; detail: string }
export interface Health { status: "ok" | "error"; checks: Record<string, HealthCheck> }

// ---- customer WS: client -> server ----
export type CustomerInbound =
  | { type: "text_input"; text: string }
  | { type: "mute"; muted: boolean }
  | { type: "language"; code: string | null };

// ---- customer WS: server -> client ----
export type CustomerOutbound =
  | { type: "state"; state: SessionState; message: string | null }
  | { type: "agent_state"; state: AgentState }
  | { type: "transcript"; speaker: "customer" | "hermion"; text: string; final: boolean }
  | { type: "tts_end" }
  | { type: "tts_stop" }
  | { type: "caption"; speaker: "customer" | "hermion"; product_name: string | null; amount: Money }
  | { type: "basket"; lines: BasketLinePublic[]; total: Money }
  | { type: "error"; code: string; message: string };

// ---- merchant WS: server -> client (push only) ----
export type MerchantOutbound =
  | { type: "session_created"; session: SessionSummary }
  | { type: "session_state"; session_id: string; state: SessionState }
  | { type: "trace"; session_id: string; kind: "message" | "offer" | "basket" | "mandate"; data: Record<string, unknown> }
  | { type: "deal_request"; session_id: string; basket: MerchantBasket };
