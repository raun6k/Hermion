"use client";

import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { rupees } from "@/lib/format";
import type { MandateProposal, Product, TraceMessage } from "@/lib/types";

function MandateCard({
  mandate,
  products,
  onConfirm,
  busy,
}: {
  mandate: MandateProposal;
  products: Product[];
  onConfirm: () => void;
  busy: boolean;
}) {
  const name = (id: string) => products.find((p) => p.product_id === id)?.product_name ?? id;
  return (
    <div className="space-y-2 rounded-lg border border-violet-300 bg-violet-50 p-3" data-testid="mandate-card">
      <p className="text-sm font-medium text-violet-900">Hermion proposes</p>
      <ul className="space-y-1 text-sm text-violet-950">
        {mandate.rules.map((r) => (
          <li key={r.product_id + (r.when.with_product_id ?? "")}>
            <span className="font-medium">{name(r.product_id)}</span>: settle at {rupees(r.settle_at)}
            {r.when.with_product_id && <> when bought with {name(r.when.with_product_id)}</>}
            {r.when.min_qty && <> when {r.when.min_qty}+ pieces</>}
            {mandate.limited_product_ids.includes(r.product_id) && (
              <span className="ml-1 rounded bg-amber-100 px-1.5 text-xs text-amber-800" data-testid="limited-note">
                held at your catalog limit
              </span>
            )}
          </li>
        ))}
      </ul>
      {mandate.confirmed ? (
        <p className="text-xs text-violet-700">Confirmed. Hermion is back with the customer.</p>
      ) : (
        <button onClick={onConfirm} disabled={busy} className="rounded bg-violet-700 px-3 py-1.5 text-sm text-white disabled:opacity-50" data-testid="confirm-mandate">
          Confirm and let Hermion continue
        </button>
      )}
    </div>
  );
}

export function Briefing({
  sessionId,
  messages,
  mandate,
  products,
  onChanged,
}: {
  sessionId: string;
  messages: TraceMessage[];
  mandate: MandateProposal | null;
  products: Product[];
  onChanged: () => void;
}) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const chat = messages.filter((m) => m.channel === "briefing");

  async function send() {
    const value = text.trim();
    if (!value || busy) return;
    setBusy(true);
    setText("");
    try {
      await api.briefing(sessionId, value);
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError && e.code === "NOT_IMPLEMENTED" ? "Briefing is not available on this backend yet." : (e as Error).message);
    } finally {
      setBusy(false);
      onChanged();
    }
  }

  async function confirm() {
    if (!mandate) return;
    setBusy(true);
    try {
      await api.confirmMandate(sessionId, mandate.mandate_id);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
      onChanged();
    }
  }

  return (
    <div className="space-y-3 rounded-2xl border border-violet-200 bg-violet-50/40 p-4" data-testid="briefing">
      <p className="text-sm font-semibold text-[#071844]">Tell Hermion what to offer <span className="font-normal text-[#415981]">(private; the customer never sees this)</span></p>
      <ol className="max-h-40 space-y-1.5 overflow-y-auto" data-testid="briefing-chat">
        {chat.length === 0 && (
          <li className="text-sm text-slate-400">e.g. “If they take the shirt at ₹850, give the belt for ₹300.”</li>
        )}
        {chat.map((m) => (
          <li key={m.id} className={`max-w-[85%] rounded-lg px-3 py-1.5 text-sm ${m.speaker === "merchant" ? "ml-auto bg-slate-900 text-white" : "bg-violet-100 text-violet-950"}`}>
            {m.text}
          </li>
        ))}
      </ol>
      {mandate && <MandateCard mandate={mandate} products={products} onConfirm={confirm} busy={busy} />}
      {error && <p className="text-sm text-red-600" role="alert">{error}</p>}
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void send();
        }}
      >
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Tell Hermion what you are happy with…" className="min-w-0 flex-1 rounded border border-slate-300 px-3 py-1.5 text-sm" data-testid="briefing-input" />
        <button disabled={busy || !text.trim()} className="rounded bg-sky-700 px-3 py-1.5 text-sm text-white disabled:opacity-40" data-testid="briefing-send">Send</button>
      </form>
    </div>
  );
}
