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

const ADDRESS_IN_DESCRIPTION = /\b(?:near|on|in)\s+([^,.;]+,\s*[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)*)\b/;

// Keep the merchant header concise while retaining the full introduction in Shop and the customer view.
export function merchantAddress(description: string): string {
  return description.match(ADDRESS_IN_DESCRIPTION)?.[1]?.trim() ?? "";
}

// What each session state means to a shopkeeper.
export const STATE_LABEL: Record<string, string> = {
  intro: "Just arrived",
  discovery: "Browsing",
  negotiating: "Bargaining",
  pending_merchant: "Needs your decision",
  briefing: "Waiting on your instructions",
  in_person: "You're talking in person",
  accepted: "Sold",
  declined: "You declined",
  exited: "Left",
};

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// "4:32 PM · 31 Oct" from an ISO string (UTC clock, like hhmm; no Date.now so it prerenders).
export function when(iso: string): string {
  const h = Number(iso.slice(11, 13));
  const time = `${h % 12 || 12}:${iso.slice(14, 16)} ${h < 12 ? "AM" : "PM"}`;
  return `${time} · ${Number(iso.slice(8, 10))} ${MONTHS[Number(iso.slice(5, 7)) - 1]}`;
}

// Language names come from the browser, never from a hardcoded list.
export function languageName(code: string): string {
  try {
    return new Intl.DisplayNames(["en"], { type: "language" }).of(code.split("-")[0]) ?? code;
  } catch {
    return code;
  }
}
