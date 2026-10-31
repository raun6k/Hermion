// In-browser stand-in for the backend (NEXT_PUBLIC_USE_MOCKS=true): same REST and WebSocket contract as
// docs/api.md, driven by the demo script (docs/scope.md#demo-script). The panes never share state; they
// only talk to this object through lib/api.ts and lib/ws.ts, exactly as they would to the real server.
// Singleton is created lazily: nothing here may run at module load (Cache Components prerender).
import { ApiError } from "@/lib/errors";
import type {
  BasketEdit,
  BriefingResponse,
  CustomerOutbound,
  Goal,
  MandateProposal,
  MerchantBasket,
  MerchantBasketLine,
  MerchantOutbound,
  MerchantProfile,
  Product,
  ProductCreate,
  ProductPatch,
  ReviewAction,
  SessionPublic,
  SessionState,
  SessionSummary,
  SessionTrace,
  Stats,
  TraceMessage,
  TraceOffer,
  BasketPublic,
  Health,
} from "@/lib/types";
import { MERCHANT, seedGoals, seedProducts } from "./fixtures";

type Listener<T> = (e: T) => void;
const money = (n: number) => n.toFixed(2);
const num = (s: string | null | undefined) => (s == null ? 0 : Number(s));
const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(v, hi));
const ceil10 = (v: number) => Math.ceil(v / 10) * 10;
const MAX_ROUNDS = 4;

interface Line {
  product_id: string;
  qty: number;
  line_total: number;
  below_minimum: boolean;
}

interface MockSession {
  id: string;
  state: SessionState;
  language: string | null;
  started_at: string;
  ended_at: string | null;
  messages: TraceMessage[];
  offers: TraceOffer[];
  basket: Line[];
  mandate: MandateProposal | null;
  rounds: Record<string, number>;
  focus: string;
  pendingBundle: { shirt: number; belt: number } | null;
  lastCounter: Record<string, number>;
  transcripts: { speaker: "customer" | "hermion"; text: string }[];
}

// Hermion's lines: [customer language (Telugu), merchant language (Hindi)].
type Say = [string, string];
const fmt = (n: number) => `₹${n.toLocaleString("en-IN")}`;
const T = {
  greet: ["నమస్కారం! నేను లక్ష్మీ ఫ్యాషన్స్ అసిస్టెంట్ హర్మియన్‌ని. మీకు ఏమి కావాలి?", "नमस्ते! मैं लक्ष्मी फैशन्स का असिस्टेंट हर्मियन हूँ। आपको क्या चाहिए?"] as Say,
  ask: ["ఎవరి కోసం? ఏ సైజ్ కావాలి?", "किसके लिए? कौन सा साइज़ चाहिए?"] as Say,
  shirt: [`నీలి కాటన్ షర్ట్ ఉంది, ${fmt(1000)}. సైజ్ M స్టాక్‌లో ఉంది. మీ ధర చెప్పండి.`, `नीली कॉटन शर्ट है, ${fmt(1000)}। साइज़ M स्टॉक में है। आप अपनी कीमत बताइए।`] as Say,
  belt: [`బ్రౌన్ లెదర్ బెల్ట్ ${fmt(500)}. మీ ధర చెప్పండి.`, `ब्राउन लेदर बेल्ट ${fmt(500)}। आप अपनी कीमत बताइए।`] as Say,
  counter: (p: number, final: boolean): Say => [
    final ? `${fmt(p)} — ఇదే నా చివరి ధర.` : `${fmt(p)} కి ఇవ్వగలను, ఇదే నా మంచి ధర.`,
    final ? `${fmt(p)} — यह मेरा आख़िरी भाव है।` : `${fmt(p)} में दे सकता हूँ, यह मेरा अच्छा भाव है।`,
  ],
  accept: (name: string, p: number): Say => [`సరే! ${name} ${fmt(p)} కి మీ బాస్కెట్‌లో వేశాను.`, `ठीक है! ${name} ${fmt(p)} में आपकी टोकरी में डाल दिया।`],
  hold: (p: number): Say => [`క్షమించండి, ధరలు మార్చే అనుమతి నాకు లేదు. ${fmt(p)} కి ఇవ్వగలను.`, `माफ़ कीजिए, भाव बदलने की इजाज़त मुझे नहीं है। ${fmt(p)} में दे सकता हूँ।`],
  pair: (p: number): Say => [`శుభవార్త! షర్ట్ + బెల్ట్ రెండూ కలిపి ${fmt(p)} కి ఇస్తాను. సరేనా?`, `अच्छी ख़बर! शर्ट + बेल्ट दोनों मिलाकर ${fmt(p)} में दूँगा। ठीक है?`],
  pairDone: ["అద్భుతం! రెండూ బాస్కెట్‌లో ఉన్నాయి. పంపించండి.", "बढ़िया! दोनों टोकरी में हैं। भेज दीजिए।"] as Say,
  reviewing: ["షాపు మీ బాస్కెట్‌ను పరిశీలిస్తోంది…", "दुकान आपकी टोकरी देख रही है…"] as Say,
  nope: ["సరే, ఇంకా ఏమైనా కావాలా?", "ठीक है, और कुछ चाहिए?"] as Say,
};

const STATE_MESSAGES: Partial<Record<SessionState, string>> = {
  pending_merchant: "The shop is reviewing your basket…",
  briefing: "The shop is reviewing your basket…",
  in_person: "The shopkeeper is coming to you",
  accepted: "Deal confirmed! The shopkeeper accepted your basket.",
  declined: "Sorry, the shop could not accept this basket. Thank you for visiting!",
};
const TERMINAL: SessionState[] = ["accepted", "declined", "exited"];

export class MockBackend {
  merchant: MerchantProfile = { ...MERCHANT, languages: [...MERCHANT.languages] };
  products: Product[] = seedProducts();
  goals: Goal[] = seedGoals();
  sessions = new Map<string, MockSession>();
  private customerSubs = new Map<string, Set<Listener<CustomerOutbound>>>();
  private merchantSubs = new Set<Listener<MerchantOutbound>>();
  private deviceSessions = new Map<string, string>();

  // ---- plumbing ---------------------------------------------------------------------
  private now(): string {
    return new Date().toISOString();
  }
  private later(ms: number, fn: () => void) {
    setTimeout(fn, ms);
  }
  private toCustomer(id: string, e: CustomerOutbound) {
    this.customerSubs.get(id)?.forEach((l) => l(e));
  }
  private toMerchant(e: MerchantOutbound) {
    this.merchantSubs.forEach((l) => l(e));
  }
  subscribeCustomer(id: string, l: Listener<CustomerOutbound>): () => void {
    const set = this.customerSubs.get(id) ?? new Set();
    set.add(l);
    this.customerSubs.set(id, set);
    return () => set.delete(l);
  }
  subscribeMerchant(l: Listener<MerchantOutbound>): () => void {
    this.merchantSubs.add(l);
    return () => this.merchantSubs.delete(l);
  }
  private product(id: string): Product {
    const p = this.products.find((x) => x.product_id === id);
    if (!p) throw new ApiError(404, "PRODUCT_NOT_FOUND", `Unknown product ${id}`);
    return p;
  }
  private session(id: string): MockSession {
    const s = this.sessions.get(id);
    if (!s) throw new ApiError(404, "SESSION_NOT_FOUND", "Unknown session");
    return s;
  }
  private summary(s: MockSession): SessionSummary {
    return {
      session_id: s.id,
      state: s.state,
      language: s.language,
      started_at: s.started_at,
      ended_at: s.ended_at,
      line_count: s.basket.length,
      basket_total: s.basket.length ? money(s.basket.reduce((a, l) => a + l.line_total, 0)) : null,
    };
  }
  private setState(s: MockSession, to: SessionState) {
    s.state = to;
    if (TERMINAL.includes(to)) s.ended_at = this.now();
    this.toCustomer(s.id, { type: "state", state: to, message: STATE_MESSAGES[to] ?? null });
    this.toMerchant({ type: "session_state", session_id: s.id, state: to });
  }
  private wrongState(s: MockSession, wanted: string): never {
    throw new ApiError(409, "WRONG_STATE", `Session is ${s.state}; this needs ${wanted}`);
  }

  // ---- customer REST ----------------------------------------------------------------
  createSession(qrToken: string, deviceId: string): { session_id: string } {
    if (qrToken !== this.merchant.qr_token) throw new ApiError(404, "UNKNOWN_QR", "This QR code does not belong to a Hermion shop");
    const live = this.deviceSessions.get(deviceId);
    if (live && !TERMINAL.includes(this.sessions.get(live)!.state))
      throw new ApiError(409, "SESSION_ACTIVE", "Exit your current session to scan again");
    const id = crypto.randomUUID();
    const s: MockSession = {
      id,
      state: "intro",
      language: "te-IN",
      started_at: this.now(),
      ended_at: null,
      messages: [],
      offers: [],
      basket: [],
      mandate: null,
      rounds: {},
      focus: "SHIRT-BLU-M",
      pendingBundle: null,
      lastCounter: {},
      transcripts: [],
    };
    this.sessions.set(id, s);
    this.deviceSessions.set(deviceId, id);
    this.toMerchant({ type: "session_created", session: this.summary(s) });
    return { session_id: id };
  }

  publicSession(id: string): SessionPublic {
    const s = this.session(id);
    return { session_id: id, state: s.state, language: s.language, languages: [...this.merchant.languages] };
  }

  confirm(id: string): { state: SessionState; basket: BasketPublic } {
    const s = this.session(id);
    if (s.state === "pending_merchant") return { state: s.state, basket: this.publicBasket(s) };
    if (s.state !== "negotiating") this.wrongState(s, "negotiating");
    if (!s.basket.length) throw new ApiError(400, "BASKET_EMPTY", "Add something to your basket first");
    this.setState(s, "pending_merchant");
    this.toMerchant({ type: "deal_request", session_id: id, basket: this.merchantBasket(s) });
    return { state: s.state, basket: this.publicBasket(s) };
  }

  exit(id: string): { state: SessionState } {
    const s = this.session(id);
    if (!TERMINAL.includes(s.state)) this.setState(s, "exited");
    return { state: s.state };
  }

  // ---- baskets ----------------------------------------------------------------------
  private publicBasket(s: MockSession): BasketPublic {
    const lines = s.basket.map((l) => ({
      product_id: l.product_id,
      product_name: this.product(l.product_id).product_name,
      qty: l.qty,
      line_total: money(l.line_total),
    }));
    return { lines, total: money(s.basket.reduce((a, l) => a + l.line_total, 0)) };
  }
  private merchantBasket(s: MockSession): MerchantBasket {
    const lines: MerchantBasketLine[] = s.basket.map((l) => {
      const p = this.product(l.product_id);
      return {
        product_id: l.product_id,
        product_name: p.product_name,
        qty: l.qty,
        listed_price: p.listed_price,
        line_total: money(l.line_total),
        contribution: money(l.line_total - num(p.unit_cost) * l.qty),
        below_minimum: l.below_minimum,
      };
    });
    return {
      lines,
      total: money(s.basket.reduce((a, l) => a + l.line_total, 0)),
      contribution: money(lines.reduce((a, l) => a + num(l.contribution), 0)),
    };
  }
  private pushBasket(s: MockSession, action: string) {
    const pub = this.publicBasket(s);
    this.toCustomer(s.id, { type: "basket", lines: pub.lines, total: pub.total });
    this.toMerchant({ type: "trace", session_id: s.id, kind: "basket", data: { action, basket: this.merchantBasket(s) } });
  }
  private setLines(s: MockSession, lines: Line[]) {
    for (const l of lines) s.basket = s.basket.filter((x) => x.product_id !== l.product_id);
    s.basket.push(...lines);
    this.pushBasket(s, "add");
  }

  // ---- the mock engine (same maths as backend/app/engine, integer rupees) --------------
  private threshold(s: MockSession, p: Product, e: number): number {
    const listed = num(p.listed_price);
    const min = num(p.minimum_price);
    const target = clamp(p.target_price == null ? (listed + min) / 2 : num(p.target_price), min, listed);
    const t = e <= MAX_ROUNDS ? listed - ((listed - target) * e) / MAX_ROUNDS : target - ((target - min) * (e - MAX_ROUNDS)) / 2;
    let v = Math.ceil(Math.max(t, min));
    const rule = s.mandate?.confirmed
      ? s.mandate.rules.find(
          (r) => r.product_id === p.product_id && (!r.when.with_product_id || s.basket.some((l) => l.product_id === r.when.with_product_id)),
        )
      : undefined;
    if (rule) v = Math.ceil(clamp(num(rule.settle_at), min, listed));
    if (!p.negotiable) v = listed;
    return v;
  }
  private evaluate(s: MockSession, p: Product, offered: number, buyNow: boolean) {
    const round = (s.rounds[p.product_id] ?? 0) + 1;
    s.rounds[p.product_id] = round;
    const signals: string[] = [];
    if (buyNow) signals.push("buy_now");
    if (s.basket.some((l) => l.product_id !== p.product_id)) signals.push("basket");
    if (this.goals.some((g) => g.goal_type === "clear_stock" && g.product_ids.includes(p.product_id))) signals.push("clear_stock");
    const t = this.threshold(s, p, Math.min(round, MAX_ROUNDS) + signals.length);
    const listed = num(p.listed_price);
    let decision: TraceOffer["decision"];
    let price: number;
    let reason: string;
    let final = false;
    if (offered >= t) {
      decision = "accept";
      price = Math.min(offered, listed);
      reason = "ACCEPTABLE";
    } else if (!p.negotiable) {
      decision = "reject";
      price = listed;
      reason = "FIXED_PRICE";
      final = true;
    } else {
      price = Math.min(ceil10(t), listed);
      if (round <= MAX_ROUNDS) {
        decision = "counter";
        final = round === MAX_ROUNDS;
        reason = final ? "FINAL_OFFER" : "COUNTER";
      } else {
        decision = "reject";
        reason = "ROUNDS_EXHAUSTED";
        final = true;
      }
    }
    const offer: TraceOffer = {
      id: crypto.randomUUID(),
      items: [{ product_id: p.product_id, qty: 1 }],
      offered_amount: money(offered),
      offer_scope: "per_unit",
      signals: { active: signals },
      decision,
      price: money(price),
      line_prices: [{ product_id: p.product_id, qty: 1, line_total: money(price) }],
      reason_code: reason,
      round,
      final,
      threshold: money(t),
      created_at: this.now(),
    };
    s.offers.push(offer);
    this.toMerchant({ type: "trace", session_id: s.id, kind: "offer", data: offer });
    return { decision, price, final };
  }

  // ---- Hermion (scripted) -----------------------------------------------------------
  private async say(s: MockSession, [te, hi]: Say, opts: { amount?: number; product?: string; mood?: "happy" } = {}) {
    this.toCustomer(s.id, { type: "agent_state", state: "speaking" });
    s.transcripts.push({ speaker: "hermion", text: te });
    this.toCustomer(s.id, { type: "transcript", speaker: "hermion", text: te, final: true });
    if (opts.amount != null)
      this.toCustomer(s.id, { type: "caption", speaker: "hermion", product_name: opts.product ?? null, amount: money(opts.amount) });
    this.record(s, "hermion", te, hi);
    this.later(700, () => {
      this.toCustomer(s.id, { type: "tts_end" });
      this.toCustomer(s.id, { type: "agent_state", state: opts.mood ?? "idle" });
      if (opts.mood) this.later(1400, () => this.toCustomer(s.id, { type: "agent_state", state: "idle" }));
    });
  }
  private record(s: MockSession, speaker: TraceMessage["speaker"], text: string, translated: string | null, channel: "customer" | "briefing" = "customer") {
    const m: TraceMessage = {
      id: crypto.randomUUID(),
      channel,
      speaker,
      text,
      language: channel === "briefing" ? "hi-IN" : "te-IN",
      text_translated: translated,
      created_at: this.now(),
    };
    s.messages.push(m);
    this.toMerchant({ type: "trace", session_id: s.id, kind: "message", data: m });
  }

  connectCustomer(id: string, onEvent: Listener<CustomerOutbound>): { send: (e: import("@/lib/types").CustomerInbound) => void; close: () => void } {
    const s = this.session(id);
    const off = this.subscribeCustomer(id, onEvent);
    // Reconnect replay: state, basket, agent_state, last transcripts.
    onEvent({ type: "state", state: s.state, message: STATE_MESSAGES[s.state] ?? null });
    if (s.basket.length) {
      const pub = this.publicBasket(s);
      onEvent({ type: "basket", lines: pub.lines, total: pub.total });
    }
    onEvent({ type: "agent_state", state: "idle" });
    s.transcripts.slice(-20).forEach((t) => onEvent({ type: "transcript", speaker: t.speaker, text: t.text, final: true }));
    if (s.state === "intro") {
      this.later(300, () => {
        this.toCustomer(id, { type: "agent_state", state: "thinking" });
        this.later(500, () => {
          this.setState(s, "discovery");
          void this.say(s, T.greet);
        });
      });
    }
    return {
      send: (e) => {
        if (e.type === "text_input") this.customerText(s, e.text);
      },
      close: off,
    };
  }

  private customerText(s: MockSession, text: string) {
    if (TERMINAL.includes(s.state)) return;
    s.transcripts.push({ speaker: "customer", text });
    this.toCustomer(s.id, { type: "transcript", speaker: "customer", text, final: true });
    this.record(s, "customer", text, text);
    this.toCustomer(s.id, { type: "agent_state", state: "thinking" });
    const amountMatch = text.replace(/,/g, "").match(/\d{3,5}/);
    const amount = amountMatch ? Number(amountMatch[0]) : null;
    if (amount != null) this.toCustomer(s.id, { type: "caption", speaker: "customer", product_name: this.product(s.focus).product_name, amount: money(amount) });
    this.later(650, () => void this.respond(s, text, amount));
  }

  private async respond(s: MockSession, text: string, amount: number | null) {
    if (s.state === "pending_merchant" || s.state === "briefing") return void this.say(s, T.reviewing);
    if (s.state === "in_person") return;
    const lower = text.toLowerCase();
    const wantsBelt = /belt|patta|పట్టా|बेल्ट|బెల్ట్/.test(lower);
    const buyNow = /now|ippude|abhi|ఇప్పుడే|अभी|take it|teesuk/.test(lower);
    const agree = /\b(ok|okay|yes|agree|deal|sare|sarey)\b|సరే|అవును|ठीक|हाँ/.test(lower);

    // After a confirmed mandate Hermion pitches the pair; the customer agrees.
    if (s.pendingBundle && agree && amount == null) {
      const { shirt, belt } = s.pendingBundle;
      s.pendingBundle = null;
      this.setLines(s, [
        { product_id: "SHIRT-BLU-M", qty: 1, line_total: shirt, below_minimum: false },
        { product_id: "BELT-BRN-32", qty: 1, line_total: belt, below_minimum: false },
      ]);
      return void this.say(s, T.pairDone, { mood: "happy" });
    }
    if (wantsBelt) s.focus = "BELT-BRN-32";
    const p = this.product(s.focus);
    const injected = /ignore|50%|you are allowed|rules|instructions/.test(lower);
    if (injected) {
      const last = s.lastCounter[p.product_id] ?? num(p.listed_price);
      return void this.say(s, T.hold(last), { amount: last, product: p.product_name });
    }
    if (amount == null) {
      if (wantsBelt) return void this.say(s, T.belt, { amount: 500, product: p.product_name });
      if (s.state === "discovery" && !s.offers.length) {
        return void this.say(s, /size|\bm\b|సైజ్/.test(lower) ? T.shirt : T.ask, { amount: /size|\bm\b|సైజ్/.test(lower) ? 1000 : undefined, product: p.product_name });
      }
      return void this.say(s, T.nope);
    }
    this.toCustomer(s.id, { type: "agent_state", state: "negotiating" });
    const r = this.evaluate(s, p, amount, buyNow);
    if (s.state === "discovery") this.setState(s, "negotiating");
    if (r.decision === "accept") {
      this.setLines(s, [{ product_id: p.product_id, qty: 1, line_total: r.price, below_minimum: false }]);
      return void this.say(s, T.accept(p.category === "belts" ? "బెల్ట్" : "షర్ట్", r.price), { amount: r.price, product: p.product_name, mood: "happy" });
    }
    s.lastCounter[p.product_id] = r.price;
    return void this.say(s, T.counter(r.price, r.final), { amount: r.price, product: p.product_name });
  }

  // ---- merchant REST ----------------------------------------------------------------
  health(): Health {
    return { status: "ok", checks: { db: { status: "fake", detail: "mock" }, openrouter: { status: "fake", detail: "mock" }, sarvam: { status: "fake", detail: "mock" } } };
  }
  getMerchant(): MerchantProfile {
    return { ...this.merchant };
  }
  patchMerchant(patch: Partial<MerchantProfile>): MerchantProfile {
    if (patch.languages && !patch.languages.length) throw new ApiError(422, "VALIDATION_ERROR", "at least one language is required", "languages");
    this.merchant = { ...this.merchant, ...patch };
    return this.getMerchant();
  }
  listProducts(): Product[] {
    return this.products.map((p) => ({ ...p }));
  }
  private validate(p: Pick<Product, "listed_price" | "target_price" | "minimum_price" | "unit_cost" | "available_stock">) {
    const [listed, min, cost] = [num(p.listed_price), num(p.minimum_price), num(p.unit_cost)];
    const bad = (field: string, message: string): never => {
      throw new ApiError(422, "VALIDATION_ERROR", message, field);
    };
    if (!(min > 0)) bad("minimum_price", "Minimum price must be above 0");
    if (min > listed) bad("minimum_price", "Minimum price cannot exceed the listed price");
    if (p.target_price != null && !(min <= num(p.target_price) && num(p.target_price) <= listed))
      bad("target_price", "Target price must be between minimum and listed price");
    if (cost < 0) bad("unit_cost", "Unit cost cannot be negative");
    if (p.available_stock < 0) bad("available_stock", "Stock cannot be negative");
    if (!Number.isInteger(listed)) bad("listed_price", "listed_price must be a whole number of rupees");
  }
  createProduct(body: ProductCreate): Product {
    if (this.products.some((p) => p.product_id === body.product_id)) throw new ApiError(409, "PRODUCT_EXISTS", `${body.product_id} already exists`, "product_id");
    this.validate(body);
    const p: Product = { ...body, merchant_id: "M001" };
    this.products.push(p);
    return { ...p };
  }
  patchProduct(id: string, patch: ProductPatch): Product {
    const p = this.product(id);
    this.validate({ ...p, ...patch });
    Object.assign(p, patch);
    return { ...p };
  }
  deleteProduct(id: string) {
    this.product(id);
    this.products = this.products.filter((p) => p.product_id !== id);
  }
  listGoals(): Goal[] {
    return this.goals.map((g) => ({ ...g }));
  }
  replaceGoals(goals: Goal[]): Goal[] {
    const known = new Set(this.products.map((p) => p.product_id));
    this.goals = goals.map((g, i) => {
      const missing = g.product_ids.filter((x) => !known.has(x));
      if (missing.length) throw new ApiError(422, "VALIDATION_ERROR", `Unknown product(s): ${missing.join(", ")}`, "product_ids");
      return { ...g, goal_id: g.goal_id.trim() || `G${String(i + 1).padStart(3, "0")}` };
    });
    return this.listGoals();
  }
  listSessions(scope: "live" | "past"): SessionSummary[] {
    return [...this.sessions.values()]
      .filter((s) => TERMINAL.includes(s.state) === (scope === "past"))
      .map((s) => this.summary(s))
      .reverse();
  }
  trace(id: string): SessionTrace {
    const s = this.session(id);
    return {
      session: this.summary(s),
      messages: s.messages.map((m) => ({ ...m })),
      offers: s.offers.map((o) => ({ ...o })),
      tool_calls: [],
      state_changes: [],
      basket: s.basket.length ? this.merchantBasket(s) : null,
      mandate: s.mandate,
    };
  }
  review(id: string, action: ReviewAction): { state: SessionState } {
    const s = this.session(id);
    if (action === "renegotiate_hermion" || action === "renegotiate_in_person") {
      if (s.state !== "pending_merchant") this.wrongState(s, "pending_merchant");
      this.setState(s, action === "renegotiate_hermion" ? "briefing" : "in_person");
      return { state: s.state };
    }
    if (s.state !== "pending_merchant" && s.state !== "in_person") this.wrongState(s, "pending_merchant or in_person");
    if (action === "accept") {
      for (const l of s.basket) {
        const p = this.product(l.product_id);
        if (l.qty > p.available_stock) throw new ApiError(409, "INSUFFICIENT_STOCK", `Only ${p.available_stock} of ${p.product_name} left`);
      }
      for (const l of s.basket) this.product(l.product_id).available_stock -= l.qty;
    }
    this.setState(s, action === "accept" ? "accepted" : "declined");
    return { state: s.state };
  }
  briefing(id: string, text: string): BriefingResponse {
    const s = this.session(id);
    if (s.state !== "briefing") this.wrongState(s, "briefing");
    this.record(s, "merchant", text, null, "briefing");
    const numbers = [...text.replace(/,/g, "").matchAll(/\d{2,5}/g)].map((m) => Number(m[0]));
    const belt = this.product("BELT-BRN-32");
    const shirt = this.product("SHIRT-BLU-M");
    if (numbers.length < 2) {
      const reply = "कौन सा सामान और किस भाव पर? उदाहरण: शर्ट ₹850 और बेल्ट ₹300 साथ में।";
      this.record(s, "hermion", reply, null, "briefing");
      return { reply, proposed_mandate: null };
    }
    const [shirtAsk, beltAsk] = [numbers[0], numbers[1]];
    const limited: string[] = [];
    const clampTo = (p: Product, v: number) => {
      const c = clamp(v, num(p.minimum_price), num(p.listed_price));
      if (c !== v) limited.push(p.product_id);
      return c;
    };
    const rules = [
      { product_id: shirt.product_id, settle_at: money(clampTo(shirt, shirtAsk)), when: { with_product_id: belt.product_id } },
      { product_id: belt.product_id, settle_at: money(clampTo(belt, beltAsk)), when: { with_product_id: shirt.product_id } },
    ];
    const proposal: MandateProposal = {
      mandate_id: crypto.randomUUID(),
      readable: `${shirt.product_name}: settle at ₹${shirtAsk} when it is bought with ${belt.product_name}\n${belt.product_name}: settle at ₹${beltAsk} when it is bought with ${shirt.product_name}`,
      rules,
      limited_product_ids: limited,
      confirmed: false,
    };
    s.mandate = proposal;
    this.toMerchant({ type: "trace", session_id: id, kind: "mandate", data: { action: "proposed", mandate: proposal } });
    const reply = limited.length
      ? "समझ गया। एक कीमत कैटलॉग की सीमा से नीचे थी, इसलिए उसे सीमा पर रखा है। कृपया कार्ड कन्फर्म करें।"
      : "समझ गया। कृपया नीचे का कार्ड कन्फर्म करें, उसके बाद ही यह लागू होगा।";
    this.record(s, "hermion", reply, null, "briefing");
    return { reply, proposed_mandate: proposal };
  }
  confirmMandate(id: string, mandateId: string): { state: SessionState } {
    const s = this.session(id);
    if (s.state !== "briefing") this.wrongState(s, "briefing");
    if (!s.mandate || s.mandate.mandate_id !== mandateId) throw new ApiError(404, "MANDATE_NOT_FOUND", "Unknown or superseded mandate");
    s.mandate = { ...s.mandate, confirmed: true };
    this.toMerchant({ type: "trace", session_id: id, kind: "mandate", data: { action: "confirmed", mandate: s.mandate } });
    this.setState(s, "negotiating");
    // Hermion resumes with the customer: pitch the pair at the mandate's prices.
    const shirt = num(s.mandate.rules[0].settle_at);
    const belt = num(s.mandate.rules[1].settle_at);
    s.pendingBundle = { shirt, belt };
    this.later(500, () => {
      this.toCustomer(id, { type: "agent_state", state: "negotiating" });
      this.later(500, () => void this.say(s, T.pair(shirt + belt), { amount: shirt + belt, product: "షర్ట్ + బెల్ట్" }));
    });
    return { state: s.state };
  }
  editBasket(id: string, body: BasketEdit): MerchantBasket {
    const s = this.session(id);
    if (s.state !== "in_person") this.wrongState(s, "in_person");
    s.basket = body.lines.map((l) => {
      const p = this.product(l.product_id);
      if (l.qty > p.available_stock) throw new ApiError(409, "INSUFFICIENT_STOCK", `Only ${p.available_stock} of ${p.product_name} left`);
      return { product_id: l.product_id, qty: l.qty, line_total: num(l.line_total), below_minimum: num(l.line_total) < num(p.minimum_price) * l.qty };
    });
    this.pushBasket(s, "edit");
    return this.merchantBasket(s);
  }
  stats(): Stats {
    const deals = [...this.sessions.values()].filter((s) => s.state === "accepted");
    let listed = 0;
    let agreed = 0;
    let contribution = 0;
    for (const s of deals)
      for (const l of s.basket) {
        const p = this.product(l.product_id);
        listed += num(p.listed_price) * l.qty;
        agreed += l.line_total;
        contribution += l.line_total - num(p.unit_cost) * l.qty;
      }
    return {
      sessions: this.sessions.size,
      offers: [...this.sessions.values()].reduce((a, s) => a + s.offers.length, 0),
      deals: deals.length,
      avg_discount_pct: money(listed ? ((listed - agreed) / listed) * 100 : 0),
      total_contribution: money(contribution),
    };
  }
}

let instance: MockBackend | null = null;
export function mockBackend(): MockBackend {
  instance ??= new MockBackend();
  return instance;
}
