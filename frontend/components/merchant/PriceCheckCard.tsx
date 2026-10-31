"use client";

// Hermion asks about an offer below the lowest price. Three answers: take it, name a price, or say no.
// Prices below a product's minimum are refused by the server; change the minimum in Products first.
import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { rupees } from "@/lib/format";
import type { PriceCheck, PriceCheckAction, Product } from "@/lib/types";

export function PriceCheckCard({
  sessionId,
  customer,
  check,
  products,
  onAnswered,
}: {
  sessionId: string;
  customer: string;
  check: PriceCheck;
  products: Product[];
  onAnswered: () => void;
}) {
  const [price, setPrice] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const names = new Map(products.map((p) => [p.product_id, p.product_name]));
  const what = check.items.map((i) => `${i.qty}× ${names.get(i.product_id) ?? i.product_id}`).join(" + ");

  async function answer(action: PriceCheckAction) {
    setBusy(true);
    try {
      await api.answerPriceCheck(sessionId, action, action === "counter" ? price.trim() : undefined);
      setError(null);
      onAnswered();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not send your answer");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="space-y-3 rounded-3xl bg-white p-5 shadow-[0_8px_30px_rgba(8,27,77,0.12)] ring-1 ring-violet-200" data-testid="price-check-card" aria-label="Hermion needs a quick answer">
      <h3 className="font-semibold text-[#071844]">{customer} wants a price below your lowest</h3>
      <p className="text-sm text-[#253d70]">
        They offered <strong>{rupees(check.offered_amount)}</strong> for {what}, under your lowest price. Hermion is waiting for your answer.
      </p>
      <div className="flex flex-wrap items-end gap-2">
        <button disabled={busy} onClick={() => answer("accept")} className="min-h-11 rounded-full bg-emerald-600 px-4 text-sm font-semibold text-white disabled:opacity-50" data-testid="check-accept">Take their offer</button>
        <label className="text-xs text-[#415981]">
          Or name a price
          <input value={price} onChange={(e) => setPrice(e.target.value)} inputMode="numeric" className="mt-0.5 block w-28 rounded border border-violet-200 px-2 py-1.5 text-sm" data-testid="check-price" />
        </label>
        <button disabled={busy || !price.trim()} onClick={() => answer("counter")} className="min-h-11 rounded-full bg-[#071f5c] px-4 text-sm font-semibold text-white disabled:opacity-50" data-testid="check-counter">Offer this price</button>
        <button disabled={busy} onClick={() => answer("decline")} className="min-h-11 rounded-full bg-white px-4 text-sm font-semibold text-slate-700 ring-1 ring-slate-300 disabled:opacity-50" data-testid="check-decline">Keep our price</button>
      </div>
      {error && <p className="text-sm text-red-600" role="alert" data-testid="check-error">{error}</p>}
    </section>
  );
}
