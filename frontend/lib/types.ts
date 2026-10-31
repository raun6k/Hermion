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
  error: { code: string; message: string; field?: string | null };
}

// ---- customer REST (public: never contains private fields) ----
export interface SessionCreate { qr_token: string; device_id: string; customer_name?: string | null }
export interface SessionCreated { session_id: string }
export interface ShopPublic { shop_name: string; languages: string[] }
export interface MerchantChoice { merchant_id: string; shop_name: string; shop_description: string; qr_token: string }
export interface SessionPublic { session_id: string; state: SessionState; language: string | null; languages: string[] }
export interface BasketLinePublic { product_id: string; product_name: string; qty: number; line_total: Money; listed_total: Money }
export interface ProductPublic {
  product_id: string;
  product_name: string;
  category: string;
  attributes: Record<string, unknown>;
  listed_price: Money;
  stock_band: "in" | "low" | "out";
  negotiable: boolean;
  pitch?: string | null;
  selling_points: string[];
  specs: Record<string, unknown>;
  best_for: string[];
}
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
  qr_token: string;
  escalation: Escalation;
  escalation_gap_pct: number;
}
export type Escalation = "never" | "serious" | "rare" | "when_close";
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
  pitch?: string | null;
  selling_points?: string[] | null;
  specs?: Record<string, unknown> | null;
  best_for?: string[] | null;
  objection_replies?: { objection: string; reply: string }[] | null;
  pairs_with_ids?: string[] | null;
  upsell_ids?: string[] | null;
}
export type GoalType = "clear_stock" | "preserve_stock" | "bigger_baskets";
export interface Goal { goal_id: string; goal_type: GoalType; product_ids: string[]; instructions: string }
export interface SessionSummary {
  session_id: string;
  state: SessionState;
  language: string | null;
  started_at: string;
  ended_at: string | null;
  line_count: number;
  basket_total: Money | null;
  customer_name?: string | null;
  display_name?: string; // the name, or "Guest N"
  price_check?: PriceCheck | null; // Hermion is waiting for the shopkeeper about one close offer
}
export interface PriceCheck { evaluation_id: string; items: { product_id: string; qty: number }[]; offered_amount: Money }
export type PriceCheckAction = "accept" | "counter" | "decline";
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
// listed_price is per unit; line_total is for the whole line (qty pieces).
export interface MerchantBasket { lines: MerchantBasketLine[]; total: Money; contribution: Money }
export type ReviewAction = "accept" | "decline" | "renegotiate_hermion" | "renegotiate_in_person";
export interface ReviewResponse { state: SessionState }
export interface MandateConfirmResponse { state: SessionState }

export type ProductBase = Omit<Product, "product_id" | "merchant_id">;
export type ProductCreate = ProductBase & { product_id: string };
export type ProductPatch = Partial<ProductBase>;
export type MerchantPatch = Partial<Omit<MerchantProfile, "merchant_id" | "qr_token">>;

export interface TraceOffer {
  id: string;
  items: { product_id: string; qty: number }[];
  offered_amount: Money;
  offer_scope: "per_unit" | "line" | "basket";
  signals: Record<string, unknown>;
  decision: "accept" | "counter" | "reject";
  price: Money | null;
  line_prices: { product_id: string; qty: number; line_total: Money }[];
  reason_code: string;
  round: number;
  final: boolean;
  threshold: Money | null; // merchant-only
  profile?: string | null;
  headroom?: string | null;
  created_at: string;
}
export interface MandateRule {
  product_id: string;
  settle_at: Money;
  when: { min_qty?: number; with_product_id?: string };
}
export interface MandateProposal {
  mandate_id: string;
  readable: string;
  rules: MandateRule[];
  limited_product_ids: string[];
  confirmed: boolean;
}
export interface TraceToolCall {
  id: string; channel: "customer" | "briefing"; name: string;
  arguments: Record<string, unknown>; result: Record<string, unknown>; created_at: string;
  evaluation_id?: string | null; // = TraceOffer.id
}
export interface TraceStateChange { id: string; from_state: SessionState; to_state: SessionState; created_at: string }
export interface TraceTiming { id: string; message_id: string; measurements: Record<string, number | string | null>; created_at: string }
export interface SessionTrace {
  session: SessionSummary;
  messages: TraceMessage[];
  offers: TraceOffer[];
  tool_calls: TraceToolCall[];
  state_changes: TraceStateChange[];
  turn_timings: TraceTiming[];
  basket: MerchantBasket | null;
  mandate: MandateProposal | null;
}
export interface BriefingResponse { reply: string; proposed_mandate: MandateProposal | null }
export interface BasketEdit { lines: { product_id: string; qty: number; line_total: Money }[] }
export interface Stats {
  sessions: number;
  offers: number;
  deals: number;
  avg_discount_pct: Money;
  total_contribution: Money;
  days?: number | null;
  revenue_won?: Money;
  discount_given?: Money;
  funnel?: { scanned: number; started: number; offered: number; in_basket: number; confirmed: number; accepted: number } | null;
  per_day?: { day: string; deals: number; revenue: Money }[];
  top_products?: { product_id: string; product_name: string; units: number; revenue: Money }[];
  language_mix?: { name: string; value: number }[];
  upsell_attach_rate?: Money;
  abandoned_baskets?: number;
  escalation_rate?: Money;
  total_negotiation_seconds?: number;
  avg_response_ms?: number | null;
  outcomes?: { name: "accepted" | "declined" | "exited" | "open"; value: number }[];
  per_hour_utc?: { name: string; value: number }[]; // name = UTC hour "0".."23"
}
export interface VisitPublic { session_id: string; state: SessionState; started_at: string; basket: BasketPublic | null }
export interface HealthCheck { status: "ok" | "fake" | "error"; detail: string }
export interface Health { status: "ok" | "error"; checks: Record<string, HealthCheck> }

// ---- customer WS: client -> server ----
export type CustomerInbound =
  | { type: "voice_start" }
  | { type: "ui_language"; code: string }
  | { type: "text_input"; text: string }
  | { type: "mute"; muted: boolean };

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
  | { type: "trace"; session_id: string; kind: "message"; data: TraceMessage }
  | { type: "trace"; session_id: string; kind: "offer"; data: TraceOffer }
  | { type: "trace"; session_id: string; kind: "tool_call"; data: TraceToolCall }
  | { type: "trace"; session_id: string; kind: "timing"; data: TraceTiming }
  | { type: "trace"; session_id: string; kind: "basket"; data: { action: string; basket: MerchantBasket } & Record<string, unknown> }
  | { type: "trace"; session_id: string; kind: "mandate"; data: { action: "proposed" | "confirmed"; mandate: MandateProposal } }
  | { type: "deal_request"; session_id: string; basket: MerchantBasket; price_check?: PriceCheck | null };
