"use client";

import { createPortal } from "react-dom";
import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";
import { api, ApiError } from "@/lib/api";
import type { Goal, GoalType, Product } from "@/lib/types";

const GOAL_TYPES: { value: GoalType; label: string; hint: string }[] = [
  { value: "clear_stock", label: "Sell these faster", hint: "Hermion gives a little more on these to move them" },
  { value: "preserve_stock", label: "Keep the price up", hint: "Hermion holds at your usual price or above" },
  { value: "bigger_baskets", label: "Sell more per customer", hint: "Hermion nudges customers to buy more together" },
];

/** Size variants of one product count once in the summary. */
function goalProducts(ids: string[], products: Product[]): string {
  const counts = new Map<string, number>();
  for (const id of ids) {
    const name = products.find((product) => product.product_id === id)?.product_name ?? id;
    counts.set(name, (counts.get(name) ?? 0) + 1);
  }
  const names = [...counts].map(([name, count]) => (count > 1 ? `${name} (${count} sizes)` : name));
  return names.length > 2 ? `${names.slice(0, 2).join("; ")} and ${names.length - 2} more` : names.join("; ");
}

function Saved({ at }: { at: number }) {
  return at ? <span className="text-sm font-medium text-emerald-700" role="status">✓ Saved</span> : null;
}

function GoalTypeSelect({ value, index, onChange }: { value: GoalType; index: number; onChange: (value: GoalType) => void }) {
  const selectedIndex = Math.max(0, GOAL_TYPES.findIndex((type) => type.value === value));
  const selected = GOAL_TYPES[selectedIndex];
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(selectedIndex);
  const [position, setPosition] = useState<CSSProperties | null>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const listbox = useRef<HTMLDivElement>(null);
  const options = useRef<Array<HTMLButtonElement | null>>([]);
  const listboxId = `goal-type-options-${index}`;

  const close = useCallback((returnFocus: boolean) => {
    setOpen(false);
    if (returnFocus) window.requestAnimationFrame(() => trigger.current?.focus());
  }, []);

  function focusOption(next: number) {
    const bounded = (next + GOAL_TYPES.length) % GOAL_TYPES.length;
    setActiveIndex(bounded);
    window.requestAnimationFrame(() => options.current[bounded]?.focus());
  }

  function show() {
    const rect = trigger.current?.getBoundingClientRect();
    if (!rect) return;
    const width = Math.min(360, Math.max(208, window.innerWidth - 24));
    const left = Math.max(12, Math.min(rect.left, window.innerWidth - width - 12));
    const height = 236;
    const top = window.innerHeight - rect.bottom >= height + 16 ? rect.bottom + 8 : Math.max(12, rect.top - height - 8);
    setPosition({ position: "fixed", top, left, width });
    setActiveIndex(selectedIndex);
    setOpen(true);
    window.requestAnimationFrame(() => options.current[selectedIndex]?.focus());
  }

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target as Node;
      if (!trigger.current?.contains(target) && !listbox.current?.contains(target)) setOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as Node;
      if (!trigger.current?.contains(target) && !listbox.current?.contains(target)) return;
      if (event.key === "Escape") {
        event.preventDefault();
        close(true);
      } else if (event.key === "ArrowDown") {
        event.preventDefault();
        focusOption(activeIndex + 1);
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        focusOption(activeIndex - 1);
      } else if (event.key === "Home") {
        event.preventDefault();
        focusOption(0);
      } else if (event.key === "End") {
        event.preventDefault();
        focusOption(GOAL_TYPES.length - 1);
      }
    };
    const closeOnViewportChange = () => setOpen(false);
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    window.addEventListener("resize", closeOnViewportChange);
    window.addEventListener("scroll", closeOnViewportChange, true);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("resize", closeOnViewportChange);
      window.removeEventListener("scroll", closeOnViewportChange, true);
    };
  }, [activeIndex, close, open]);

  return (
    <div className="min-w-0 flex-1">
      <button
        ref={trigger}
        type="button"
        aria-label={`Goal type: ${selected.label}`}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listboxId}
        data-testid={`goal-type-select-${index}`}
        onClick={() => open ? close(false) : show()}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            event.preventDefault();
            show();
          }
        }}
        className={`group flex min-h-[60px] w-full items-center justify-between gap-3 rounded-2xl border bg-white px-3 py-2.5 text-left shadow-sm transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-pink-200 ${open ? "border-pink-300" : "border-sky-200 hover:border-pink-300 hover:shadow-md"}`}
      >
        <span className="min-w-0">
          <span className="block text-[10px] font-bold uppercase tracking-[0.12em] text-[#5b6f94]">Goal type</span>
          <span className="mt-0.5 block truncate text-sm font-bold text-[#071844]">{selected.label}</span>
          <span className="mt-0.5 block text-xs leading-4 text-[#415981]">{selected.hint}</span>
        </span>
        <span className={`grid h-9 w-9 shrink-0 place-items-center rounded-full transition ${open ? "bg-pink-600 text-white" : "bg-sky-50 text-[#071f5c] group-hover:bg-pink-50"}`} aria-hidden="true">
          <svg viewBox="0 0 20 20" className={`h-4 w-4 transition-transform ${open ? "rotate-180" : ""}`} fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="m5 7.5 5 5 5-5" /></svg>
        </span>
      </button>
      {open && position && createPortal(
        <div
          ref={listbox}
          id={listboxId}
          role="listbox"
          aria-label="Goal type"
          className="z-[100] max-h-72 overflow-y-auto rounded-2xl border border-sky-200 bg-white p-2 text-[#071844] shadow-[0_18px_45px_rgba(8,27,77,0.2)] ring-1 ring-white"
          style={position}
          onBlur={(event) => {
            const next = event.relatedTarget as Node | null;
            if (next && !event.currentTarget.contains(next) && !trigger.current?.contains(next)) setOpen(false);
          }}
        >
          {GOAL_TYPES.map((type, optionIndex) => {
            const isSelected = type.value === value;
            return (
              <button
                key={type.value}
                ref={(node) => { options.current[optionIndex] = node; }}
                type="button"
                role="option"
                aria-selected={isSelected}
                tabIndex={activeIndex === optionIndex ? 0 : -1}
                onMouseEnter={() => setActiveIndex(optionIndex)}
                onClick={() => { onChange(type.value); close(true); }}
                className={`flex min-h-[62px] w-full items-center justify-between gap-3 rounded-xl px-3 py-2 text-left transition ${isSelected ? "bg-sky-50" : "hover:bg-sky-50/70"}`}
              >
                <span className="min-w-0">
                  <span className="block text-sm font-semibold text-[#071844]">{type.label}</span>
                  <span className="mt-0.5 block text-xs leading-4 text-[#415981]">{type.hint}</span>
                </span>
                <span className={`grid h-6 w-6 shrink-0 place-items-center rounded-full ${isSelected ? "bg-pink-600 text-white" : "border border-sky-200 text-transparent"}`} aria-hidden="true">
                  <svg viewBox="0 0 16 16" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m3 8 3.2 3.2L13 4.5" /></svg>
                </span>
              </button>
            );
          })}
        </div>,
        document.body,
      )}
    </div>
  );
}

export function Goals({ products, merchantId }: { products: Product[]; merchantId: string | null }) {
  const [data, setData] = useState<{ merchantId: string; goals: Goal[] } | null>(null);
  const [error, setError] = useState<{ merchantId: string; message: string } | null>(null);
  const [reloadCount, setReloadCount] = useState(0);
  const [saving, setSaving] = useState(false);
  const [savedFor, setSavedFor] = useState<string | null>(null);
  const goals = data?.merchantId === merchantId ? data.goals : null;
  const goalError = error?.merchantId === merchantId ? error.message : null;

  useEffect(() => {
    let current = true;
    if (!merchantId) return () => { current = false; };
    api.goals(merchantId).then((items) => {
      if (current) {
        setData({ merchantId, goals: items });
        setError((previous) => previous?.merchantId === merchantId ? null : previous);
      }
    }).catch((e: unknown) => {
      if (!current) return;
      setError({ merchantId, message: e instanceof ApiError ? e.message : "Could not load goals" });
    });
    return () => { current = false; };
  }, [merchantId, reloadCount]);

  async function saveGoals() {
    if (goals === null || !merchantId) return;
    setSaving(true);
    try {
      setData({ merchantId, goals: await api.replaceGoals(goals) });
      setError((previous) => previous?.merchantId === merchantId ? null : previous);
      setSavedFor(merchantId);
    } catch (e) {
      setSavedFor(null);
      setError({ merchantId, message: e instanceof ApiError ? e.message : "Could not save goals" });
    } finally {
      setSaving(false);
    }
  }

  const updateGoals = (update: (current: Goal[]) => Goal[]) => {
    if (!merchantId) return;
    setData((current) => current?.merchantId === merchantId ? { ...current, goals: update(current.goals) } : current);
  };
  const updateGoal = (index: number, patch: Partial<Goal>) =>
    updateGoals((current) => current.map((goal, n) => (n === index ? { ...goal, ...patch } : goal)));
  const field = "mt-1 w-full rounded-xl border border-sky-200 bg-white px-3 py-2 text-sm text-[#071844] focus:border-pink-400 focus:outline-none focus:ring-2 focus:ring-pink-100";
  const card = "space-y-4 rounded-3xl bg-white p-5 shadow-[0_8px_30px_rgba(8,27,77,0.08)] ring-1 ring-sky-100 sm:p-6";
  const primary = "min-h-11 rounded-full bg-[#071f5c] px-5 text-sm font-semibold text-white hover:bg-[#0b2a78] disabled:cursor-not-allowed disabled:opacity-50";

  return (
    <section className={card} data-testid="goals">
      <div>
        <h2 className="text-base font-bold text-[#071844]">Shop goals</h2>
        <p className="mt-1 max-w-2xl text-sm leading-6 text-[#415981]">
          Focus Hermion on products already in your catalog. Goals guide its recommendations while each offer stays within the product’s price limits.
        </p>
      </div>

      {goals === null && !goalError && <p className="text-sm text-[#415981]" role="status">{merchantId ? "Loading goals…" : "Loading shop…"}</p>}
      {goalError && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-red-50 px-3 py-3 text-sm text-red-700" role="alert">
          <span>{goalError}</span>
          {goals === null && <button className="min-h-10 rounded-full px-4 font-semibold ring-1 ring-red-200 hover:bg-white" onClick={() => { setError(null); setReloadCount((n) => n + 1); }}>Try again</button>}
        </div>
      )}

      {goals?.length === 0 && <p className="rounded-2xl border border-dashed border-sky-200 px-3 py-4 text-center text-sm text-[#415981]">No goals yet. Add one to give Hermion a clear focus.</p>}

      {goals?.map((goal, index) => (
        <div key={goal.goal_id || index} className="space-y-3 rounded-2xl border border-sky-100 bg-sky-50/50 p-3 sm:p-4">
          <div className="flex flex-wrap items-start gap-3">
            <GoalTypeSelect value={goal.goal_type} index={index} onChange={(goal_type) => updateGoal(index, { goal_type })} />
            <button
              className="ml-auto min-h-10 rounded-full px-3 text-xs text-slate-500 hover:bg-white hover:text-red-600"
              onClick={() => updateGoals((current) => current.filter((_, n) => n !== index))}
              aria-label={`Remove goal ${index + 1}`}
            >
              Remove
            </button>
          </div>

          <details className="text-sm">
            <summary className="min-h-10 cursor-pointer content-center font-medium text-[#253d70]">
              {goal.product_ids.length ? goalProducts(goal.product_ids, products) : "All products"}
            </summary>
            {products.length > 0 ? (
              <div className="mt-2 grid max-h-44 grid-cols-1 gap-1 overflow-y-auto rounded-xl bg-white p-2 sm:grid-cols-2">
                {products.map((product) => (
                  <label key={product.product_id} className="flex min-h-9 items-start gap-2 rounded-lg px-1 py-1 text-xs leading-5 text-[#071844] hover:bg-sky-50">
                    <input
                      type="checkbox"
                      className="mt-1 h-4 w-4 shrink-0 accent-pink-600"
                      checked={goal.product_ids.includes(product.product_id)}
                      onChange={(e) => updateGoal(index, {
                        product_ids: e.target.checked
                          ? [...goal.product_ids, product.product_id]
                          : goal.product_ids.filter((id) => id !== product.product_id),
                      })}
                    />
                    <span>
                      {product.product_name}
                      {Object.values(product.attributes).length > 0 && <span className="text-[#5b6f94]"> · {Object.values(product.attributes).slice(0, 2).join(", ")}</span>}
                    </span>
                  </label>
                ))}
              </div>
            ) : (
              <p className="mt-2 rounded-xl bg-white px-3 py-2 text-xs text-[#5b6f94]">Add products to your catalog to focus a goal on specific items. This goal currently applies to the whole shop.</p>
            )}
          </details>

          <label className="block text-sm font-medium text-[#253d70]">
            Goal guidance <span className="font-normal text-[#5b6f94]">(optional)</span>
            <textarea
              className={field}
              rows={2}
              value={goal.instructions}
              placeholder="Add a short note about how Hermion should handle these products."
              onChange={(e) => updateGoal(index, { instructions: e.target.value })}
              aria-label={`Instructions for goal ${index + 1}`}
            />
          </label>
        </div>
      ))}

      <div className="flex flex-wrap items-center gap-3">
        <button
          className="min-h-11 rounded-full px-4 text-sm font-semibold text-[#071844] ring-1 ring-sky-200 hover:bg-sky-50 disabled:cursor-not-allowed disabled:opacity-50"
          disabled={goals === null || !merchantId}
          onClick={() => updateGoals((current) => [...current, { goal_id: "", goal_type: "clear_stock", product_ids: [], instructions: "" }])}
        >
          + Add goal
        </button>
        <button className={primary} disabled={goals === null || saving} onClick={saveGoals} data-testid="save-goals">
          {saving ? "Saving…" : "Save goals"}
        </button>
        <Saved at={savedFor === merchantId ? 1 : 0} />
      </div>
    </section>
  );
}
