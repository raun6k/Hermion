"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { Goal, GoalType, MerchantProfile, Product } from "@/lib/types";

const GOAL_TYPES: { value: GoalType; label: string; hint: string }[] = [
  { value: "clear_stock", label: "Clear stock", hint: "Concede a little faster on these products" },
  { value: "preserve_stock", label: "Preserve stock", hint: "Hold at or above target" },
  { value: "bigger_baskets", label: "Bigger baskets", hint: "Encourage buying more together" },
];

function Saved({ at }: { at: number }) {
  return at ? <span className="text-sm text-emerald-700" role="status">Saved</span> : null;
}

export function Shop({ shop, onSaved, products }: { shop: MerchantProfile; onSaved: (m: MerchantProfile) => void; products: Product[] }) {
  const [draft, setDraft] = useState({
    shop_name: shop.shop_name,
    shop_description: shop.shop_description,
    languages: shop.languages.join(", "),
    negotiation_instructions: shop.negotiation_instructions,
    bundle_allowed: shop.bundle_allowed,
  });
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(0);
  const [goals, setGoals] = useState<Goal[] | null>(null);
  const [goalError, setGoalError] = useState<string | null>(null);
  const [goalsSaved, setGoalsSaved] = useState(0);

  useEffect(() => {
    api.goals().then(setGoals).catch(() => setGoals([]));
  }, []);

  async function save() {
    try {
      onSaved(
        await api.patchMerchant({
          ...draft,
          languages: draft.languages.split(",").map((l) => l.trim()).filter(Boolean),
        }),
      );
      setError(null);
      setSaved((n) => n + 1);
    } catch (e) {
      setSaved(0);
      setError(e instanceof ApiError ? e.message : "Could not save");
    }
  }

  async function saveGoals() {
    try {
      setGoals(await api.replaceGoals(goals ?? []));
      setGoalError(null);
      setGoalsSaved((n) => n + 1);
    } catch (e) {
      setGoalsSaved(0);
      setGoalError(e instanceof ApiError ? e.message : "Could not save goals");
    }
  }

  const updateGoal = (i: number, patch: Partial<Goal>) => setGoals((g) => (g ?? []).map((x, n) => (n === i ? { ...x, ...patch } : x)));
  const field = "mt-1 w-full rounded border border-slate-300 px-2 py-1.5 text-sm";

  return (
    <div className="grid gap-6 lg:grid-cols-2" data-testid="shop-settings">
      <section className="space-y-3 rounded-lg border border-slate-200 bg-white p-4">
        <h3 className="font-medium text-slate-800">Shop</h3>
        <label className="block text-sm text-slate-600">
          Name
          <input className={field} value={draft.shop_name} onChange={(e) => setDraft({ ...draft, shop_name: e.target.value })} data-testid="shop-name-input" />
        </label>
        <label className="block text-sm text-slate-600">
          Description (Hermion introduces the shop with this)
          <textarea className={field} rows={2} value={draft.shop_description} onChange={(e) => setDraft({ ...draft, shop_description: e.target.value })} />
        </label>
        <label className="block text-sm text-slate-600">
          Languages (first is yours; the rest are the customer languages you serve)
          <input className={field} value={draft.languages} onChange={(e) => setDraft({ ...draft, languages: e.target.value })} data-testid="languages-input" />
        </label>
        <label className="block text-sm text-slate-600">
          Negotiation style (wording and tactics only; never changes your limits)
          <textarea className={field} rows={3} value={draft.negotiation_instructions} onChange={(e) => setDraft({ ...draft, negotiation_instructions: e.target.value })} />
        </label>
        <label className="flex items-center gap-2 text-sm text-slate-700">
          <input type="checkbox" checked={draft.bundle_allowed} onChange={(e) => setDraft({ ...draft, bundle_allowed: e.target.checked })} />
          Allow bundle (basket) offers
        </label>
        {error && <p className="text-sm text-red-600" role="alert" data-testid="shop-error">{error}</p>}
        <div className="flex items-center gap-3">
          <button onClick={save} className="rounded bg-sky-700 px-3 py-1.5 text-sm text-white" data-testid="save-shop">Save shop</button>
          <Saved at={saved} />
        </div>
      </section>

      <section className="space-y-3 rounded-lg border border-slate-200 bg-white p-4" data-testid="goals">
        <h3 className="font-medium text-slate-800">Goals</h3>
        {(goals ?? []).map((g, i) => (
          <div key={i} className="space-y-2 rounded border border-slate-200 p-3">
            <div className="flex items-center gap-2">
              <select className="rounded border border-slate-300 px-2 py-1 text-sm" value={g.goal_type} onChange={(e) => updateGoal(i, { goal_type: e.target.value as GoalType })} aria-label="Goal type">
                {GOAL_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </select>
              <span className="text-xs text-slate-500">{GOAL_TYPES.find((t) => t.value === g.goal_type)?.hint}</span>
              <button className="ml-auto text-xs text-slate-400 hover:text-red-600" onClick={() => setGoals((all) => (all ?? []).filter((_, n) => n !== i))}>Remove</button>
            </div>
            <details className="text-sm">
              <summary className="cursor-pointer text-slate-600">
                {g.product_ids.length ? `${g.product_ids.length} product(s)` : "Whole shop"}
              </summary>
              <div className="mt-1 grid max-h-32 grid-cols-2 gap-1 overflow-y-auto">
                {products.map((p) => (
                  <label key={p.product_id} className="flex items-center gap-1 text-xs">
                    <input
                      type="checkbox"
                      checked={g.product_ids.includes(p.product_id)}
                      onChange={(e) =>
                        updateGoal(i, { product_ids: e.target.checked ? [...g.product_ids, p.product_id] : g.product_ids.filter((x) => x !== p.product_id) })
                      }
                    />
                    {p.product_id}
                  </label>
                ))}
              </div>
            </details>
            <textarea className={field} rows={2} value={g.instructions} placeholder="Instructions for Hermion (wording only)" onChange={(e) => updateGoal(i, { instructions: e.target.value })} />
          </div>
        ))}
        {goalError && <p className="text-sm text-red-600" role="alert">{goalError}</p>}
        <div className="flex items-center gap-3">
          <button className="rounded border px-3 py-1.5 text-sm" onClick={() => setGoals((g) => [...(g ?? []), { goal_id: "", goal_type: "clear_stock", product_ids: [], instructions: "" }])}>
            + Add goal
          </button>
          <button className="rounded bg-sky-700 px-3 py-1.5 text-sm text-white" onClick={saveGoals} data-testid="save-goals">Save goals</button>
          <Saved at={goalsSaved} />
        </div>
      </section>
    </div>
  );
}
