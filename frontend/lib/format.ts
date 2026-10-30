// Display helpers. No Date.now()/Math.random() (Cache Components prerender); parsing a given ISO string is fine.
export const num = (s: string | null | undefined): number => (s == null || s === "" ? 0 : Number(s));

export function rupees(v: string | number | null | undefined): string {
  const n = typeof v === "number" ? v : num(v);
  return `₹${n.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
}

export function hhmm(iso: string): string {
  return iso.slice(11, 16);
}

export function shortId(id: string): string {
  return id.slice(0, 8);
}

export const STATE_LABEL: Record<string, string> = {
  intro: "intro",
  discovery: "discovery",
  negotiating: "negotiating",
  pending_merchant: "awaiting your decision",
  briefing: "briefing Hermion",
  in_person: "in person",
  accepted: "accepted",
  declined: "declined",
  exited: "exited",
};
