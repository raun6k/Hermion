"use client";

// The basket is its own page (docs/upgrades-plan.md 5): a receipt-style card with each line, what it saves
// against the listed price, the total and a prominent Confirm. Reached from the basket pill at the top of the call.
import { useEffect, useRef } from "react";
import { rupees } from "@/lib/format";
import { translate } from "@/lib/i18n";
import type { BasketLinePublic } from "@/lib/types";

export function BasketSheet({
  lang,
  lines,
  total,
  busy,
  error,
  onConfirm,
  onRemove,
  onClose,
}: {
  lang: string;
  lines: BasketLinePublic[];
  total: string;
  busy: boolean;
  error: string | null;
  onConfirm: () => void;
  onRemove: (productId: string) => void;
  onClose: () => void;
}) {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => heading.current?.focus(), []);
  const saved = lines.reduce((a, l) => a + Math.max(Number(l.listed_total) - Number(l.line_total), 0), 0);
  return (
    <main className="absolute inset-0 z-30 flex flex-col bg-[#062a86] pt-9 text-white" data-testid="basket-sheet" aria-label={translate(lang, "basketTitle")}>
      <header className="flex items-center justify-between px-5 pb-2">
        <h1 ref={heading} tabIndex={-1} className="text-lg font-bold outline-none">{translate(lang, "basketTitle")}</h1>
        <button onClick={onClose} className="min-h-11 rounded-full bg-white/15 px-4 text-sm" aria-label={translate(lang, "backToCall")}>{translate(lang, "close")}</button>
      </header>
      <div className="mx-4 flex-1 overflow-y-auto rounded-3xl bg-white p-4 text-slate-900 shadow-xl">
        <p className="sr-only" aria-live="polite">{translate(lang, "basketTitle")}: {lines.length} · {translate(lang, "total")} {rupees(total)}</p>
        {lines.length === 0 ? (
          <p className="py-10 text-center text-sm text-slate-500">{translate(lang, "basketEmpty")}</p>
        ) : (
          <ul className="divide-y divide-dashed divide-slate-200" data-testid="basket-lines">
            {lines.map((l) => {
              const save = Number(l.listed_total) - Number(l.line_total);
              return (
                <li key={l.product_id} className="flex items-start gap-2 py-3">
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-semibold leading-tight">{l.product_name}</p>
                    <p className="mt-0.5 text-xs text-slate-500">{translate(lang, "quantity")} {l.qty}</p>
                    {save > 0 && <p className="text-xs font-medium text-emerald-700">{translate(lang, "youSave")} {rupees(save)} <span className="text-slate-400 line-through">{rupees(l.listed_total)}</span></p>}
                  </div>
                  <div className="text-right">
                    <p className="text-sm font-bold tabular-nums">{rupees(l.line_total)}</p>
                    <button onClick={() => onRemove(l.product_id)} className="min-h-11 px-1 text-xs text-slate-500 underline" aria-label={`${translate(lang, "remove")}: ${l.product_name}`}>{translate(lang, "remove")}</button>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
        {saved > 0 && <p className="mt-1 rounded-xl bg-emerald-50 px-3 py-1.5 text-xs font-medium text-emerald-800">{translate(lang, "totalSaving")} {rupees(saved)}</p>}
        <p className="mt-3 flex justify-between border-t border-slate-200 pt-3 text-base font-bold"><span>{translate(lang, "total")}</span><span data-testid="basket-total">{rupees(total)}</span></p>
      </div>
      {error && <p className="mx-4 mt-2 rounded-xl bg-white px-3 py-2 text-sm text-red-600" role="alert" data-testid="confirm-error">{error}</p>}
      <div className="p-4">
        <button onClick={onConfirm} disabled={busy || lines.length === 0} className="min-h-12 w-full rounded-2xl bg-pink-300 py-3 text-sm font-bold text-blue-950 shadow-lg disabled:opacity-50" data-testid="confirm-send">
          {translate(lang, "confirmSend")}
        </button>
      </div>
    </main>
  );
}
