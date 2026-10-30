"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { hhmm, rupees } from "@/lib/format";
import type { Product, SessionTrace, TraceMessage, TraceOffer } from "@/lib/types";

type Item = { at: string; kind: "message"; m: TraceMessage } | { at: string; kind: "offer"; o: TraceOffer };

const DECISION_STYLE: Record<string, string> = {
  accept: "bg-emerald-100 text-emerald-800",
  counter: "bg-amber-100 text-amber-800",
  reject: "bg-red-100 text-red-700",
};

export function TraceView({ sessionId, version, products }: { sessionId: string; version: number; products: Product[] }) {
  const [trace, setTrace] = useState<SessionTrace | null>(null);
  const [error, setError] = useState<string | null>(null);
  const names = new Map(products.map((p) => [p.product_id, p.product_name]));

  useEffect(() => {
    let live = true;
    api.trace(sessionId).then((t) => live && (setTrace(t), setError(null))).catch((e: Error) => live && setError(e.message));
    return () => {
      live = false;
    };
  }, [sessionId, version]);

  if (error) return <p className="p-4 text-sm text-red-600">{error}</p>;
  if (!trace) return <p className="p-4 text-sm text-slate-400">Loading trace…</p>;

  const items: Item[] = [
    ...trace.messages.map((m): Item => ({ at: m.created_at, kind: "message", m })),
    ...trace.offers.map((o): Item => ({ at: o.created_at, kind: "offer", o })),
  ].sort((a, b) => a.at.localeCompare(b.at));

  return (
    <div className="space-y-3 p-4" data-testid="trace-view">
      <p className="text-xs text-slate-500">
        Session {sessionId.slice(0, 8)} · {trace.session.state} · {trace.session.language ?? "language not detected yet"}
      </p>
      <ol className="space-y-2">
        {items.length === 0 && <li className="text-sm text-slate-400">No activity yet.</li>}
        {items.map((it) =>
          it.kind === "message" ? (
            <li key={it.m.id} className={`rounded-lg px-3 py-2 text-sm ${it.m.channel === "briefing" ? "border border-violet-200 bg-violet-50" : it.m.speaker === "customer" ? "bg-slate-100" : "bg-sky-50"}`} data-testid="trace-message">
              <div className="mb-0.5 flex gap-2 text-xs text-slate-500">
                <span className="font-medium">{it.m.channel === "briefing" ? `briefing · ${it.m.speaker}` : it.m.speaker}</span>
                <span>{hhmm(it.m.created_at)}</span>
              </div>
              <div className="text-slate-900">{it.m.text_translated ?? it.m.text}</div>
              {it.m.text_translated && it.m.text_translated !== it.m.text && <div className="mt-0.5 text-xs text-slate-500">{it.m.text}</div>}
            </li>
          ) : (
            <li key={it.o.id} className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm" data-testid="trace-offer">
              <div className="flex flex-wrap items-center gap-2">
                <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${DECISION_STYLE[it.o.decision]}`}>{it.o.decision}</span>
                <span className="font-medium text-slate-800">{it.o.items.map((i) => `${i.qty}× ${names.get(i.product_id) ?? i.product_id}`).join(" + ")}</span>
                <span className="text-xs text-slate-500">{hhmm(it.o.created_at)}</span>
              </div>
              <dl className="mt-1 grid grid-cols-3 gap-x-4 text-xs text-slate-600 sm:grid-cols-6">
                <div><dt className="text-slate-400">Customer offered</dt><dd>{rupees(it.o.offered_amount)}</dd></div>
                <div><dt className="text-slate-400">Engine price</dt><dd>{it.o.price ? rupees(it.o.price) : "–"}</dd></div>
                <div><dt className="text-slate-400">Threshold</dt><dd>{it.o.threshold ? rupees(it.o.threshold) : "–"}</dd></div>
                <div><dt className="text-slate-400">Round</dt><dd>{it.o.round}{it.o.final ? " · final" : ""}</dd></div>
                <div><dt className="text-slate-400">Reason</dt><dd>{it.o.reason_code}</dd></div>
                <div><dt className="text-slate-400">Signals</dt><dd>{((it.o.signals.active as string[] | undefined) ?? []).join(", ") || "–"}</dd></div>
              </dl>
            </li>
          ),
        )}
      </ol>
      {trace.mandate && (
        <div className="rounded-lg border border-violet-200 bg-violet-50 p-3 text-sm">
          <p className="font-medium text-violet-900">Mandate {trace.mandate.confirmed ? "(confirmed)" : "(proposed)"}</p>
          <pre className="whitespace-pre-wrap text-xs text-violet-900">{trace.mandate.readable}</pre>
        </div>
      )}
      {trace.basket && (
        <div className="rounded-lg border border-slate-200 bg-white p-3 text-sm">
          <p className="font-medium text-slate-800">Basket · {rupees(trace.basket.total)} · contribution {rupees(trace.basket.contribution)}</p>
          <ul className="text-xs text-slate-600">
            {trace.basket.lines.map((l) => (
              <li key={l.product_id}>{l.qty}× {l.product_name} — {rupees(l.line_total)}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
