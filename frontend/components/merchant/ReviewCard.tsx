"use client";

import { useEffect, useId, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { num, rupees, STATE_LABEL, when } from "@/lib/format";
import type { Product, ReviewAction, SessionTrace } from "@/lib/types";
import { Briefing } from "./Briefing";

interface EditLine {
  product_id: string;
  qty: string;
  line_total: string;
}

export function ReviewCard({
  sessionId,
  version,
  products,
  onOpenTrace,
  onChanged,
}: {
  sessionId: string;
  version: number;
  products: Product[];
  onOpenTrace: (id: string) => void;
  onChanged: () => void;
}) {
  const [trace, setTrace] = useState<SessionTrace | null>(null);
  const [menu, setMenu] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [edits, setEdits] = useState<EditLine[] | null>(null);
  const [busy, setBusy] = useState(false);
  const titleId = useId();

  useEffect(() => {
    let live = true;
    api.trace(sessionId).then((t) => live && setTrace(t)).catch((e: Error) => live && setError(e.message));
    return () => {
      live = false;
    };
  }, [sessionId, version]);

  const state = trace?.session.state;
  // Entering in_person seeds the editable lines from the basket; leaving it clears them.
  const editing = state === "in_person" && trace?.basket != null;
  const [wasEditing, setWasEditing] = useState(false);
  if (editing !== wasEditing) {
    setWasEditing(editing);
    setEdits(
      editing && trace?.basket
        ? trace.basket.lines.map((l) => ({ product_id: l.product_id, qty: String(l.qty), line_total: String(Math.round(num(l.line_total))) }))
        : null,
    );
  }

  if (!trace) return <div className="rounded-3xl bg-white p-5 text-sm text-slate-400 shadow-sm">{error ?? "Loading basket…"}</div>;

  const min = (id: string) => num(products.find((p) => p.product_id === id)?.minimum_price);
  const dirty =
    edits != null &&
    JSON.stringify(edits.map((e) => [e.product_id, Number(e.qty), Number(e.line_total)])) !==
      JSON.stringify((trace.basket?.lines ?? []).map((l) => [l.product_id, l.qty, Math.round(num(l.line_total))]));

  async function act(action: ReviewAction) {
    setBusy(true);
    setMenu(false);
    try {
      if (action === "accept" && dirty) await saveEdits();
      await api.review(sessionId, action);
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not complete that");
    } finally {
      setBusy(false);
      onChanged();
    }
  }

  async function saveEdits() {
    if (!edits) return;
    await api.editBasket(sessionId, {
      lines: edits.map((e) => ({ product_id: e.product_id, qty: Number(e.qty), line_total: e.line_total })),
    });
    onChanged();
  }

  const basket = trace.basket;
  const inPerson = state === "in_person";
  const who = trace.session.display_name || trace.session.customer_name || "A customer";
  const items = basket?.lines.reduce((n, l) => n + l.qty, 0) ?? 0;
  const btn = "min-h-11 rounded-full px-5 text-sm font-semibold transition disabled:opacity-50";
  return (
    <section
      className="overflow-hidden rounded-3xl bg-white shadow-[0_8px_30px_rgba(8,27,77,0.12)] ring-1 ring-sky-100"
      data-testid="review-card"
      data-state={state}
      aria-labelledby={titleId}
    >
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-sky-100 bg-gradient-to-r from-pink-50 to-white px-5 py-4">
        <div className="flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-2xl bg-pink-600 text-base font-bold text-white" aria-hidden>{who.slice(0, 1)}</span>
          <div>
            <h3 id={titleId} className="text-base font-bold text-[#071844]">{who}&apos;s basket</h3>
            <p className="text-xs text-[#415981]">
              {when(trace.session.started_at)} · {items} {items === 1 ? "item" : "items"} ·{" "}
              <span className="font-semibold text-pink-700">{STATE_LABEL[state ?? ""] ?? state}</span>
            </p>
          </div>
        </div>
        <button onClick={() => onOpenTrace(sessionId)} className="min-h-10 rounded-full px-3 text-sm font-medium text-sky-800 underline-offset-4 hover:underline" data-testid="open-trace">View conversation</button>
      </header>

      <div className="space-y-4 p-5">
      {basket && (
        <table className="w-full text-sm" data-testid="review-lines">
          <caption className="sr-only">Items in {who}&apos;s basket with the listed and agreed prices</caption>
          <thead className="text-left text-[11px] font-semibold uppercase tracking-wide text-[#5b6f94]">
            <tr>
              <th scope="col" className="pb-2">Item</th>
              <th scope="col" className="pb-2 text-right">Qty</th>
              <th scope="col" className="pb-2 text-right">Listed</th>
              <th scope="col" className="pb-2 text-right">Agreed</th>
              <th scope="col" className="pb-2 text-right">Discount</th>
              <th scope="col" className="pb-2 text-right">Your profit</th>
            </tr>
          </thead>
          <tbody>
            {basket.lines.map((l, i) => {
              const edit = inPerson ? edits?.[i] : null;
              const qty = edit ? Number(edit.qty) || 0 : l.qty;
              const agreed = edit ? num(edit.line_total) : num(l.line_total);
              const listed = num(l.listed_price) * qty;
              const cost = num(l.line_total) - num(l.contribution);
              const unitCost = l.qty ? cost / l.qty : 0;
              const below = edit ? agreed < min(l.product_id) * qty : l.below_minimum;
              return (
                <tr key={l.product_id} className="border-t border-slate-100" data-testid="review-line">
                  <th scope="row" className="py-2.5 pr-2 text-left font-medium text-[#071844]">
                    {l.product_name}
                    {below && <span className="ml-2 rounded-full bg-red-100 px-2 py-0.5 text-[11px] font-semibold text-red-700" data-testid="below-minimum">below your lowest price</span>}
                  </th>
                  <td className="text-right">
                    {edit ? (
                      <input value={edit.qty} inputMode="numeric" onChange={(e) => setEdits(edits!.map((x, n) => (n === i ? { ...x, qty: e.target.value } : x)))} className="min-h-10 w-14 rounded-lg border border-slate-300 px-2 text-right" aria-label={`Quantity of ${l.product_name}`} />
                    ) : l.qty}
                  </td>
                  <td className="text-right tabular-nums text-slate-500">{rupees(listed)}</td>
                  <td className="text-right font-semibold tabular-nums text-[#071844]">
                    {edit ? (
                      <input value={edit.line_total} inputMode="numeric" onChange={(e) => setEdits(edits!.map((x, n) => (n === i ? { ...x, line_total: e.target.value } : x)))} className={`min-h-10 w-24 rounded-lg border px-2 text-right ${below ? "border-red-400" : "border-slate-300"}`} aria-label={`Agreed price for ${l.product_name}`} aria-invalid={below || undefined} data-testid={`edit-total-${l.product_id}`} />
                    ) : rupees(agreed)}
                  </td>
                  <td className="text-right tabular-nums text-slate-500">{listed ? `${(((listed - agreed) / listed) * 100).toFixed(0)}%` : "–"}</td>
                  <td className="text-right tabular-nums text-emerald-700">{rupees(agreed - unitCost * qty)}</td>
                </tr>
              );
            })}
          </tbody>
          <tfoot>
            <tr className="border-t-2 border-slate-200 text-base font-bold text-[#071844]">
              <th scope="row" colSpan={3} className="pt-3 text-left">Total</th>
              <td className="pt-3 text-right tabular-nums" data-testid="review-total">{rupees(edits ? edits.reduce((a, e) => a + num(e.line_total), 0) : basket.total)}</td>
              <td />
              <td className="pt-3 text-right tabular-nums text-emerald-700">{rupees(basket.contribution)}</td>
            </tr>
          </tfoot>
        </table>
      )}

      {state === "briefing" && (
        <Briefing sessionId={sessionId} messages={trace.messages} mandate={trace.mandate} products={products} onChanged={onChanged} />
      )}
      {error && <p className="rounded-xl bg-red-50 px-3 py-2 text-sm text-red-700" role="alert" data-testid="review-error">{error}</p>}

      {(state === "pending_merchant" || inPerson) && (
        <div className="relative flex flex-wrap items-center gap-2 border-t border-slate-100 pt-4" role="group" aria-label={`Your decision on ${who}'s basket`}>
          <button disabled={busy} onClick={() => act("accept")} className={`${btn} bg-emerald-600 text-white hover:bg-emerald-700`} data-testid="accept">Accept</button>
          <button disabled={busy} onClick={() => act("decline")} className={`${btn} bg-white text-red-700 ring-1 ring-red-300 hover:bg-red-50`} data-testid="decline">Decline</button>
          {state === "pending_merchant" && (
            <div className="relative" onKeyDown={(e) => e.key === "Escape" && setMenu(false)}>
              <button disabled={busy} onClick={() => setMenu((m) => !m)} className={`${btn} bg-white text-[#071844] ring-1 ring-slate-300 hover:bg-slate-50`} aria-expanded={menu} aria-haspopup="true" data-testid="renegotiate">Renegotiate ▾</button>
              {menu && (
                <ul className="absolute left-0 top-full z-10 mt-1 w-56 overflow-hidden rounded-2xl border border-slate-200 bg-white text-sm shadow-lg">
                  <li><button autoFocus className="min-h-11 w-full px-4 text-left hover:bg-slate-50" onClick={() => act("renegotiate_hermion")} data-testid="brief-hermion">Tell Hermion what to offer</button></li>
                  <li><button className="min-h-11 w-full px-4 text-left hover:bg-slate-50" onClick={() => act("renegotiate_in_person")} data-testid="in-person">Talk to them in person</button></li>
                </ul>
              )}
            </div>
          )}
          {inPerson && dirty && (
            <button disabled={busy} onClick={() => saveEdits().catch((e: Error) => setError(e.message))} className={`${btn} bg-sky-700 text-white`} data-testid="save-edits">Save changes</button>
          )}
        </div>
      )}
      </div>
    </section>
  );
}
