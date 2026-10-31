"use client";

// One customer's conversation for the shopkeeper (docs/frontend.md#merchant-console): a summary (who, when,
// language, status, how long it took, how fast Hermion answered), then a call-style timeline of what was said
// with each price moment as a card. "Why this price?" opens the engine's reasoning for that offer; the price
// path on the side jumps to and opens an offer.
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { COPY, duration, reasonText, responseTime } from "@/lib/copy";
import { hhmm, languageName, rupees, STATE_LABEL, when } from "@/lib/format";
import type { Product, SessionTrace, TraceMessage, TraceOffer, TraceTiming } from "@/lib/types";

type Item = { at: string; kind: "message"; m: TraceMessage } | { at: string; kind: "offer"; o: TraceOffer };

const DECISION_STYLE: Record<string, string> = {
  accept: "bg-emerald-100 text-emerald-800",
  counter: "bg-amber-100 text-amber-800",
  reject: "bg-red-100 text-red-700",
};
const SIGNAL_TEXT: Record<string, string> = {
  buy_now: "said they would buy right away",
  qty: "is buying more than one",
  basket: "already has other items in the basket",
  clear_stock: "this item is on your clear-stock goal",
};
const ROOM_TEXT: Record<string, string> = {
  high: "plenty of room left to your lowest price",
  medium: "some room left",
  low: "close to your lowest price",
  none: "at your lowest price",
};

function seconds(a: string, b: string): number {
  return Math.max(0, Math.round((Date.parse(b) - Date.parse(a)) / 1000));
}

/** Total time from scan to the last word, and Hermion's average reply time across turns. */
function timing(trace: SessionTrace): { total: number | null; reply: number | null } {
  const last = trace.session.ended_at ?? trace.messages.at(-1)?.created_at ?? null;
  const replies = trace.turn_timings
    .map((t: TraceTiming) => Number(t.measurements.agent_ms ?? NaN))
    .filter((v) => Number.isFinite(v));
  return {
    total: last ? seconds(trace.session.started_at, last) : null,
    reply: replies.length ? replies.reduce((a, b) => a + b, 0) / replies.length : null,
  };
}

export function TraceView({ sessionId, version, products }: { sessionId: string; version: number; products: Product[] }) {
  const [trace, setTrace] = useState<SessionTrace | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<Set<string>>(new Set());
  const offerRefs = useRef(new Map<string, HTMLLIElement>());
  const names = new Map(products.map((p) => [p.product_id, p.product_name]));

  useEffect(() => {
    let live = true;
    api.trace(sessionId).then((t) => live && (setTrace(t), setError(null))).catch((e: Error) => live && setError(e.message));
    return () => {
      live = false;
    };
  }, [sessionId, version]);

  if (error) return <p className="p-4 text-sm text-red-600">{error}</p>;
  if (!trace) return <p className="p-4 text-sm text-slate-400">{COPY.log.loading}</p>;

  const items: Item[] = [
    ...trace.messages.map((m): Item => ({ at: m.created_at, kind: "message", m })),
    ...trace.offers.map((o): Item => ({ at: o.created_at, kind: "offer", o })),
  ].sort((a, b) => a.at.localeCompare(b.at));

  const customerName = trace.session.display_name || "Customer";
  const lastMessage = [...trace.messages].reverse().find((m) => m.channel === "customer");
  const thinking = lastMessage?.speaker === "customer" && ["discovery", "negotiating"].includes(trace.session.state);
  const { total, reply } = timing(trace);
  const what = (o: TraceOffer) => o.items.map((i) => `${i.qty > 1 ? `${i.qty}× ` : ""}${names.get(i.product_id) ?? i.product_id}`).join(" + ");
  const toggle = (id: string) => setOpen((s) => {
    const next = new Set(s);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    return next;
  });
  const jump = (id: string) => {
    setOpen((s) => new Set(s).add(id));
    offerRefs.current.get(id)?.scrollIntoView({ behavior: "smooth", block: "center" });
  };

  return (
    <div className="space-y-4 p-4" data-testid="trace-view">
      <header className="rounded-2xl bg-gradient-to-r from-sky-50 to-pink-50 p-4">
        <div className="flex flex-wrap items-center gap-3">
          <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-[#071f5c] text-base font-bold text-white" aria-hidden>{customerName.slice(0, 1)}</span>
          <div className="min-w-0 flex-1">
            <h2 className="truncate text-base font-bold text-[#071844]">{customerName}</h2>
            <p className="text-xs text-[#415981]">
              {when(trace.session.started_at)}
              {trace.session.language ? ` · speaks ${languageName(trace.session.language)}` : ""}
            </p>
          </div>
          <span className="rounded-full bg-white px-3 py-1 text-xs font-semibold text-pink-700 shadow-sm">{STATE_LABEL[trace.session.state] ?? trace.session.state}</span>
        </div>
        <dl className="mt-3 grid grid-cols-2 gap-2 text-sm sm:grid-cols-4" data-testid="session-summary">
          {[
            ["Negotiation time", total == null ? "–" : duration(total)],
            ["Hermion's reply time", reply == null ? "–" : `${responseTime(reply)} avg`],
            ["Price offers", String(trace.offers.filter((o) => o.round > 0).length)],
            ["Basket", trace.basket ? rupees(trace.basket.total) : "Empty"],
          ].map(([k, v]) => (
            <div key={k} className="rounded-xl bg-white/80 px-3 py-2">
              <dt className="text-[11px] text-[#415981]">{k}</dt>
              <dd className="font-semibold tabular-nums text-[#071844]">{v}</dd>
            </div>
          ))}
        </dl>
      </header>

      <div className="grid gap-4 lg:grid-cols-[1fr_12rem]">
        <section aria-label={COPY.log.title}>
          <ol className="relative space-y-1 before:absolute before:bottom-2 before:left-[3.85rem] before:top-2 before:w-px before:bg-sky-100">
            {items.length === 0 && <li className="text-sm text-slate-400">{COPY.log.empty}</li>}
            {items.map((it) =>
              it.kind === "message" ? (
                <li key={it.m.id} className="relative grid grid-cols-[2.75rem_1.5rem_1fr] items-start gap-2 py-1.5" data-testid="trace-message">
                  <time className="pt-0.5 text-right text-[11px] tabular-nums text-slate-400">{hhmm(it.m.created_at)}</time>
                  <span
                    className={`z-10 flex h-6 w-6 items-center justify-center rounded-full text-[10px] font-bold text-white ${it.m.channel === "briefing" ? "bg-violet-600" : it.m.speaker === "customer" ? "bg-[#071f5c]" : "bg-pink-600"}`}
                    aria-hidden
                  >
                    {it.m.channel === "briefing" ? "Y" : it.m.speaker === "customer" ? customerName.slice(0, 1) : "✦"}
                  </span>
                  <div className="min-w-0">
                    <p className="text-xs font-semibold text-[#253d70]">{it.m.channel === "briefing" ? "You told Hermion" : it.m.speaker === "customer" ? customerName : "Hermion"}</p>
                    <p className="text-sm leading-snug text-[#071844]">{it.m.text_translated ?? it.m.text}</p>
                    {it.m.text_translated && it.m.text_translated !== it.m.text && <p className="mt-0.5 text-xs text-slate-500">{it.m.text}</p>}
                  </div>
                </li>
              ) : (
                <li
                  key={it.o.id}
                  ref={(el) => {
                    if (el) offerRefs.current.set(it.o.id, el);
                  }}
                  className="relative grid grid-cols-[2.75rem_1.5rem_1fr] items-start gap-2 py-1.5"
                  data-testid="trace-offer"
                >
                  <time className="pt-2 text-right text-[11px] tabular-nums text-slate-400">{hhmm(it.o.created_at)}</time>
                  <span className="z-10 mt-1.5 flex h-6 w-6 items-center justify-center rounded-full bg-amber-400 text-xs font-bold text-[#071844]" aria-hidden>₹</span>
                  <div className="rounded-2xl border border-amber-100 bg-amber-50/60 px-3 py-2">
                    <div className="flex flex-wrap items-center gap-2 text-sm">
                      <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${DECISION_STYLE[it.o.decision]}`}>{COPY.offer.decision[it.o.decision] ?? it.o.decision}</span>
                      <span className="font-medium text-[#071844]">{what(it.o)}</span>
                    </div>
                    <p className="mt-1 flex flex-wrap items-center gap-1.5 text-sm text-[#253d70]">
                      <span>{COPY.offer.customerOffered} <strong className="tabular-nums">{rupees(it.o.offered_amount)}</strong></span>
                      {it.o.price != null && (
                        <>
                          <span aria-hidden className="text-slate-400">→</span>
                          <span>{COPY.offer.ourPrice} <strong className="tabular-nums text-pink-700">{rupees(it.o.price)}</strong></span>
                        </>
                      )}
                    </p>
                    <button
                      type="button"
                      onClick={() => toggle(it.o.id)}
                      aria-expanded={open.has(it.o.id)}
                      className="mt-1 min-h-8 text-xs font-semibold text-sky-800 underline-offset-4 hover:underline"
                      data-testid="offer-why"
                    >
                      {open.has(it.o.id) ? "Hide details" : "Why this price?"}
                    </button>
                    {open.has(it.o.id) && (
                      <ul className="mt-1 list-disc space-y-0.5 pl-4 text-xs text-[#253d70]" data-testid="offer-details">
                        <li>{reasonText(it.o.reason_code)}</li>
                        {it.o.round > 0 && <li>{COPY.offer.counter} {it.o.round} of 4{it.o.final ? ` (${COPY.offer.final})` : ""}.</li>}
                        {((it.o.signals.active as string[] | undefined) ?? []).map((s) => SIGNAL_TEXT[s] && <li key={s}>Gave a little more because the customer {SIGNAL_TEXT[s]}.</li>)}
                        {it.o.profile && <li>Customer seemed: {(COPY.profiles[it.o.profile] ?? it.o.profile).toLowerCase()}.</li>}
                        {it.o.headroom && <li>Price was {ROOM_TEXT[it.o.headroom] ?? it.o.headroom}.</li>}
                        {it.o.threshold != null && <li>Hermion would agree at {rupees(it.o.threshold)} or more at this point.</li>}
                        {Boolean(it.o.signals.escalation_eligible) && <li>Below your lowest price, so Hermion could ask you.</li>}
                      </ul>
                    )}
                  </div>
                </li>
              ),
            )}
          </ol>
          {thinking && <p className="ml-[4.75rem] mt-1 text-xs italic text-[#415981]" role="status" data-testid="thinking">Hermion is thinking…</p>}
        </section>

        <aside className="hidden lg:block" aria-label="Price path">
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-[#415981]">Price path</h3>
          <ol className="space-y-1.5">
            {trace.offers.length === 0 && <li className="text-xs text-slate-400">No offers yet</li>}
            {trace.offers.map((o) => (
              <li key={o.id}>
                <button type="button" onClick={() => jump(o.id)} className="w-full rounded-xl px-2 py-1.5 text-left text-xs hover:bg-sky-50">
                  <span className="font-semibold tabular-nums text-[#071844]">{rupees(o.offered_amount)}{o.price != null ? ` → ${rupees(o.price)}` : ""}</span>
                  <span className="block text-slate-500">{COPY.offer.decision[o.decision] ?? o.decision}</span>
                </button>
              </li>
            ))}
          </ol>
        </aside>
      </div>

      {trace.mandate && (
        <div className="rounded-2xl border border-violet-200 bg-violet-50 p-3 text-sm">
          <p className="font-semibold text-violet-900">{trace.mandate.confirmed ? COPY.mandate.confirmed : COPY.mandate.proposed}</p>
          <p className="whitespace-pre-wrap text-xs text-violet-900">{trace.mandate.readable}</p>
        </div>
      )}
      {trace.basket && (
        <div className="rounded-2xl border border-sky-100 bg-white p-3 text-sm">
          <p className="font-semibold text-[#071844]">
            Basket · {rupees(trace.basket.total)} <span className="font-normal text-emerald-700">· your profit {rupees(trace.basket.contribution)}</span>
          </p>
          <ul className="mt-1 text-xs text-[#415981]">
            {trace.basket.lines.map((l) => (
              <li key={l.product_id}>{l.qty}× {l.product_name} · {rupees(l.line_total)}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
