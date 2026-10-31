"use client";

import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { Escalation, MerchantProfile } from "@/lib/types";

const ESCALATION_HELP: Record<Escalation, string> = {
  serious: "Hermion can ask you about a qualifying offer below the lowest price when the customer appears ready to buy. The engine still protects every price limit.",
  rare: "Hermion can ask you about a near-floor offer when the customer shows clear buying intent. Set how close the offer must be below.",
  when_close: "Hermion can ask you when an offer is within the selected percentage of your lowest price.",
  never: "Hermion handles the negotiation on its own. The engine still protects every price limit.",
};

function Saved({ at }: { at: number }) {
  return at ? <span className="text-sm font-medium text-emerald-700" role="status">✓ Saved</span> : null;
}

export function Shop({ shop, onSaved }: { shop: MerchantProfile; onSaved: (m: MerchantProfile) => void }) {
  const [draft, setDraft] = useState({
    shop_name: shop.shop_name,
    shop_description: shop.shop_description,
    escalation: shop.escalation,
    escalation_gap_pct: shop.escalation_gap_pct,
    negotiation_instructions: shop.negotiation_instructions,
  });
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(0);
  const [saving, setSaving] = useState(false);

  async function save() {
    setSaving(true);
    try {
      onSaved(await api.patchMerchant(draft));
      setError(null);
      setSaved((n) => n + 1);
    } catch (e) {
      setSaved(0);
      setError(e instanceof ApiError ? e.message : "Could not save shop settings");
    } finally {
      setSaving(false);
    }
  }

  const field = "mt-1 w-full rounded-xl border border-sky-200 bg-white px-3 py-2 text-sm leading-6 text-[#071844] focus:border-pink-400 focus:outline-none focus:ring-2 focus:ring-pink-100";
  const label = "block text-sm font-medium text-[#253d70]";
  const card = "max-w-3xl space-y-5 rounded-3xl bg-white p-5 shadow-[0_8px_30px_rgba(8,27,77,0.08)] ring-1 ring-sky-100 sm:p-6";
  const primary = "min-h-11 rounded-full bg-[#071f5c] px-5 text-sm font-semibold text-white hover:bg-[#0b2a78] disabled:cursor-wait disabled:opacity-60";

  return (
    <div className="space-y-4" data-testid="shop-settings">
      <section className={card}>
        <div>
          <h3 className="text-base font-bold text-[#071844]">Your shop</h3>
          <p className="mt-1 text-sm leading-6 text-[#415981]">Edit the words Hermion uses and choose when a negotiation needs your judgment.</p>
        </div>

        <label className={label}>
          Shop name
          <input className={field} value={draft.shop_name} onChange={(e) => setDraft({ ...draft, shop_name: e.target.value })} data-testid="shop-name-input" />
        </label>

        <label className={label}>
          About the shop <span className="font-normal text-[#5b6f94]">(Hermion uses this to introduce your shop)</span>
          <textarea className={field} rows={4} value={draft.shop_description} onChange={(e) => setDraft({ ...draft, shop_description: e.target.value })} />
        </label>

        <label className={label}>
          How Hermion should bargain <span className="font-normal text-[#5b6f94]">(tone and guidance; product price limits still apply)</span>
          <textarea className={field} rows={6} value={draft.negotiation_instructions} onChange={(e) => setDraft({ ...draft, negotiation_instructions: e.target.value })} />
        </label>

        <div>
          <label className={label}>
            When should Hermion ask you to step in?
            <select
              className={field}
              value={draft.escalation}
              onChange={(e) => setDraft({ ...draft, escalation: e.target.value as Escalation })}
              aria-describedby="escalation-help"
              data-testid="escalation-select"
            >
              <option value="serious">For a below-lowest offer from a serious buyer</option>
              <option value="rare">Rarely, for a close offer from a keen buyer</option>
              <option value="when_close">Whenever an offer is close</option>
              <option value="never">Never, Hermion decides alone</option>
            </select>
          </label>
          <p id="escalation-help" className="mt-2 text-xs leading-5 text-[#5b6f94]" aria-live="polite">
            {ESCALATION_HELP[draft.escalation]}
          </p>
        </div>

        {(draft.escalation === "rare" || draft.escalation === "when_close") && (
          <label className={label}>
            “Close” means within this percent of your lowest price
            <input
              type="number"
              min={0}
              max={50}
              className={field}
              value={draft.escalation_gap_pct}
              onChange={(e) => setDraft({ ...draft, escalation_gap_pct: Number(e.target.value) })}
              data-testid="escalation-gap"
            />
          </label>
        )}

        {error && <p className="text-sm text-red-600" role="alert" data-testid="shop-error">{error}</p>}
        <div className="flex items-center gap-3">
          <button onClick={save} disabled={saving} className={primary} data-testid="save-shop">
            {saving ? "Saving…" : "Save changes"}
          </button>
          <Saved at={saved} />
        </div>
      </section>
    </div>
  );
}
