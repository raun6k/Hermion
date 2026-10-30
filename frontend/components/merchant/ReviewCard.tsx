"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { num, rupees, shortId } from "@/lib/format";
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

  if (!trace) return <div className="rounded-lg border border-slate-200 bg-white p-4 text-sm text-slate-400">{error ?? "Loading basket…"}</div>;

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
  return (
    <section className="space-y-3 rounded-xl border-2 border-pink-400 bg-pink-50 p-4" data-testid="review-card" data-state={state}>
      <header className="flex items-baseline justify-between">
        <h3 className="font-semibold text-slate-900">Basket for review · #{shortId(sessionId)}</h3>
        <button onClick={() => onOpenTrace(sessionId)} className="text-sm text-sky-700 underline" data-testid="open-trace">View trace</button>
      </header>

      {basket && (
        <table className="w-full text-sm" data-testid="review-lines">
          <thead className="text-left text-xs uppercase text-slate-500">
            <tr><th>Item</th><th className="text-right">Qty</th><th className="text-right">Listed</th><th className="text-right">Agreed</th><th className="text-right">Discount</th><th className="text-right">Contribution</th></tr>
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
                <tr key={l.product_id} className="border-t border-pink-200" data-testid="review-line">
                  <td className="py-1.5 pr-2">{l.product_name}{below && <span className="ml-1 rounded bg-red-100 px-1.5 text-xs text-red-700" data-testid="below-minimum">below minimum</span>}</td>
                  <td className="text-right">
                    {edit ? (
                      <input value={edit.qty} onChange={(e) => setEdits(edits!.map((x, n) => (n === i ? { ...x, qty: e.target.value } : x)))} className="w-12 rounded border px-1 text-right" aria-label={`Quantity ${l.product_id}`} />
                    ) : l.qty}
                  </td>
                  <td className="text-right tabular-nums">{rupees(listed)}</td>
                  <td className="text-right tabular-nums">
                    {edit ? (
                      <input value={edit.line_total} onChange={(e) => setEdits(edits!.map((x, n) => (n === i ? { ...x, line_total: e.target.value } : x)))} className={`w-20 rounded border px-1 text-right ${below ? "border-red-400" : ""}`} aria-label={`Agreed ${l.product_id}`} data-testid={`edit-total-${l.product_id}`} />
                    ) : rupees(agreed)}
                  </td>
                  <td className="text-right tabular-nums text-slate-600">{listed ? `${(((listed - agreed) / listed) * 100).toFixed(0)}%` : "–"}</td>
                  <td className="text-right tabular-nums">{rupees(agreed - unitCost * qty)}</td>
                </tr>
              );
            })}
          </tbody>
          <tfoot>
            <tr className="border-t-2 border-pink-300 font-semibold">
              <td colSpan={3}>Total</td>
              <td className="text-right tabular-nums" data-testid="review-total">{rupees(edits ? edits.reduce((a, e) => a + num(e.line_total), 0) : basket.total)}</td>
              <td />
              <td className="text-right tabular-nums">{rupees(basket.contribution)}</td>
            </tr>
          </tfoot>
        </table>
      )}

      {state === "briefing" && (
        <Briefing sessionId={sessionId} messages={trace.messages} mandate={trace.mandate} products={products} onChanged={onChanged} />
      )}
      {error && <p className="text-sm text-red-600" role="alert" data-testid="review-error">{error}</p>}

      {(state === "pending_merchant" || inPerson) && (
        <div className="relative flex flex-wrap items-center gap-2">
          <button disabled={busy} onClick={() => act("accept")} className="rounded bg-emerald-600 px-4 py-1.5 text-sm font-medium text-white disabled:opacity-50" data-testid="accept">Accept</button>
          <button disabled={busy} onClick={() => act("decline")} className="rounded bg-white px-4 py-1.5 text-sm font-medium text-red-700 ring-1 ring-red-300 disabled:opacity-50" data-testid="decline">Decline</button>
          {state === "pending_merchant" && (
            <div className="relative">
              <button disabled={busy} onClick={() => setMenu((m) => !m)} className="rounded bg-white px-4 py-1.5 text-sm font-medium text-slate-800 ring-1 ring-slate-300" aria-expanded={menu} data-testid="renegotiate">Renegotiate ▾</button>
              {menu && (
                <ul className="absolute left-0 top-full z-10 mt-1 w-44 overflow-hidden rounded-lg border border-slate-200 bg-white text-sm shadow-lg">
                  <li><button className="w-full px-3 py-2 text-left hover:bg-slate-50" onClick={() => act("renegotiate_hermion")} data-testid="brief-hermion">Brief Hermion</button></li>
                  <li><button className="w-full px-3 py-2 text-left hover:bg-slate-50" onClick={() => act("renegotiate_in_person")} data-testid="in-person">In person</button></li>
                </ul>
              )}
            </div>
          )}
          {inPerson && dirty && (
            <button disabled={busy} onClick={() => saveEdits().catch((e: Error) => setError(e.message))} className="rounded bg-sky-700 px-3 py-1.5 text-sm text-white" data-testid="save-edits">Save changes</button>
          )}
        </div>
      )}
    </section>
  );
}
