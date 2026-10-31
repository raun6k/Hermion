// Merchant-facing wording in one place. Developer terms are renamed here, never in the components
// (docs/frontend.md#merchant-console): Trace -> Conversation, Mandate -> Special instruction, Round -> Counter,
// listed / target / minimum price -> shelf price / price you aim for / lowest price.
export const COPY = {
  tabs: { catalog: "Products", shop: "Shop", sessions: "Customers", review: "Approvals", stats: "Insights" },
  review: {
    title: "Waiting for your decision",
    empty: "Nothing to approve right now. When a customer sends a basket, or Hermion needs you for a price, it shows up here.",
    waiting: (n: number) => (n === 1 ? "1 customer is waiting for you" : `${n} customers are waiting for you`),
  },
  log: { title: "Conversation", empty: "No activity yet.", loading: "Loading conversation…" },
  mandate: { proposed: "Special instruction (waiting for you)", confirmed: "Special instruction (active)" },
  offer: {
    customerOffered: "Customer offered",
    ourPrice: "Our price",
    counter: "Counter",
    final: "last counter",
    decision: { accept: "Agreed", counter: "Countered", reject: "Declined" } as Record<string, string>,
  },
  reasons: {
    ACCEPTABLE: "The offer was good enough.",
    CLOSING_BELOW_TARGET: "Closed a little under the usual price to win the sale.",
    COUNTER: "Hermion made a counter offer.",
    FINAL_OFFER: "This was Hermion's best price.",
    ROUNDS_EXHAUSTED: "Hermion had used up the counters.",
    FIXED_PRICE: "This item has a fixed price.",
    PROPOSAL_BELOW_FLOOR: "Hermion's first idea was too low, so a safer price was used.",
    HELD_FOR_MORE: "The offer was fine, but Hermion asked for a little more.",
  } as Record<string, string>,
  profiles: {
    lowballer: "Starting very low",
    value_seeker: "Looking for value",
    ready_to_buy: "Ready to buy",
    browsing: "Just browsing",
  } as Record<string, string>,
  stats: {
    revenue: "Revenue won",
    discount: "Discount given",
    avgDiscount: "Average discount",
    negotiationTime: "Total negotiation time",
    responseTime: "Average response time",
  },
} as const;

export function reasonText(code: string): string {
  return COPY.reasons[code] ?? "Hermion followed the shop's price rules.";
}

export function duration(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  return `${m}m ${String(seconds % 60).padStart(2, "0")}s`;
}

export function responseTime(ms: number | null | undefined): string {
  if (ms == null) return "–";
  if (ms < 100) return "<0.1s";
  return `${(ms / 1000).toFixed(1)}s`;
}
