import { rupees } from "@/lib/format";
import type { BasketLinePublic } from "@/lib/types";

export function BasketChip({ count, total, onClick }: { count: number; total: string; onClick: () => void }) {
  return (
    <button onClick={onClick} className="mx-auto mt-2 flex items-center gap-1.5 rounded-full bg-white px-4 py-1.5 text-sm font-semibold text-blue-950 shadow" data-testid="basket-chip" aria-label="Open basket">
      <span aria-hidden>🛒</span>
      <span>
        {count} · {rupees(total)}
      </span>
    </button>
  );
}

export function BasketSheet({
  lines,
  total,
  busy,
  error,
  onConfirm,
  onClose,
}: {
  lines: BasketLinePublic[];
  total: string;
  busy: boolean;
  error: string | null;
  onConfirm: () => void;
  onClose: () => void;
}) {
  return (
    <div className="absolute inset-x-0 bottom-0 z-20 rounded-t-3xl bg-white p-4 text-slate-900 shadow-[0_-8px_30px_rgba(0,0,0,0.35)]" data-testid="basket-sheet" role="dialog" aria-label="Your basket">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="font-semibold text-slate-900">Your basket</h2>
        <button onClick={onClose} className="text-sm text-slate-500" aria-label="Close basket">Close</button>
      </div>
      <ul className="divide-y divide-slate-100 text-sm" data-testid="basket-lines">
        {lines.map((l) => (
          <li key={l.product_id} className="flex justify-between py-2">
            <span>{l.qty > 1 ? `${l.qty} × ` : ""}{l.product_name}</span>
            <span className="font-medium tabular-nums">{rupees(l.line_total)}</span>
          </li>
        ))}
      </ul>
      <p className="mt-2 flex justify-between border-t border-slate-200 pt-2 font-semibold"><span>Total</span><span data-testid="basket-total">{rupees(total)}</span></p>
      {error && <p className="mt-2 text-sm text-red-600" role="alert" data-testid="confirm-error">{error}</p>}
      <button onClick={onConfirm} disabled={busy || lines.length === 0} className="mt-3 w-full rounded-xl bg-blue-900 py-3 text-sm font-semibold text-white disabled:opacity-50" data-testid="confirm-send">
        Confirm &amp; send to merchant
      </button>
    </div>
  );
}
