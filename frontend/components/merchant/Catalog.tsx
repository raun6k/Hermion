"use client";

import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { rupees } from "@/lib/format";
import type { Product, ProductCreate } from "@/lib/types";
import { Goals } from "./Goals";

type NumField = "listed_price" | "target_price" | "minimum_price" | "unit_cost" | "available_stock";
const COLUMNS: { field: NumField; label: string; hint?: string }[] = [
  { field: "listed_price", label: "Shelf price" },
  { field: "target_price", label: "Price you aim for", hint: "blank = halfway" },
  { field: "minimum_price", label: "Lowest price" },
  { field: "unit_cost", label: "Cost" },
  { field: "available_stock", label: "Stock" },
];

function EditableCell({
  product,
  field,
  label,
  onSaved,
}: {
  product: Product;
  field: NumField;
  label: string;
  onSaved: (p: Product) => void;
}) {
  const current = product[field] == null ? "" : field === "available_stock" ? String(product[field]) : String(Math.round(Number(product[field])));
  const [value, setValue] = useState(current);
  const [error, setError] = useState<string | null>(null);
  const [synced, setSynced] = useState(current);
  if (current !== synced) {
    setSynced(current);
    setValue(current);
  }

  async function commit() {
    if (value === current) return setError(null);
    try {
      const body =
        field === "available_stock"
          ? { available_stock: Number(value) }
          : { [field]: value.trim() === "" && field === "target_price" ? null : value.trim() };
      onSaved(await api.patchProduct(product.product_id, body));
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not save");
    }
  }

  return (
    <div className="min-w-0">
      <label htmlFor={`${product.product_id}-${field}`} className="block text-xs font-semibold text-[#415981]">{label}</label>
      <div className={`mt-1 flex min-h-11 items-center rounded-xl border bg-white px-3 transition focus-within:ring-2 ${error ? "border-red-300 bg-red-50 focus-within:ring-red-100" : "border-sky-200 focus-within:border-pink-400 focus-within:ring-pink-100"}`}>
        {field !== "available_stock" && <span className="mr-1 text-sm font-medium text-[#5b6f94]">₹</span>}
        <input
          id={`${product.product_id}-${field}`}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => {
            if (e.key === "Enter") e.currentTarget.blur();
            if (e.key === "Escape") {
              setValue(current);
              setError(null);
            }
          }}
          inputMode="numeric"
          aria-label={`${product.product_id} ${field}`}
          aria-invalid={error ? true : undefined}
          data-testid={`cell-${product.product_id}-${field}`}
          className="min-w-0 flex-1 bg-transparent text-right text-base font-semibold tabular-nums text-[#071844] outline-none"
        />
      </div>
      {error && (
        <p className="mt-1 text-xs leading-4 text-red-700" role="alert" data-testid={`error-${product.product_id}-${field}`}>
          {error}
        </p>
      )}
    </div>
  );
}

const BLANK: ProductCreate = {
  product_id: "",
  product_name: "",
  category: "",
  attributes: {},
  aliases: [],
  listed_price: "",
  target_price: null,
  minimum_price: "",
  unit_cost: "",
  available_stock: 0,
  negotiable: true,
};

function AddProduct({ onAdded }: { onAdded: (p: Product) => void }) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(BLANK);
  const [error, setError] = useState<{ field: string | null; message: string } | null>(null);
  const set = (patch: Partial<ProductCreate>) => setDraft((d) => ({ ...d, ...patch }));
  const input = (field: keyof ProductCreate, label: string, props: { wide?: boolean } = {}) => (
    <label className="flex flex-col text-xs text-slate-600">
      {label}
      <input
        value={String(draft[field] ?? "")}
        onChange={(e) => set({ [field]: field === "available_stock" ? Number(e.target.value) : e.target.value } as Partial<ProductCreate>)}
        className={`mt-0.5 rounded border px-2 py-1 text-sm ${props.wide ? "w-56" : "w-24"} ${error?.field === field ? "border-red-400" : "border-slate-300"}`}
        data-testid={`new-${field}`}
      />
    </label>
  );

  async function submit() {
    try {
      onAdded(
        await api.createProduct({
          ...draft,
          target_price: draft.target_price === "" ? null : draft.target_price,
          aliases: [],
        }),
      );
      setDraft(BLANK);
      setOpen(false);
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? { field: e.field, message: e.message } : { field: null, message: "Could not add" });
    }
  }

  if (!open)
    return (
      <button onClick={() => setOpen(true)} className="rounded border border-dashed border-slate-300 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50" data-testid="add-product">
        + Add product
      </button>
    );
  return (
    <div className="space-y-2 rounded-lg border border-slate-200 bg-slate-50 p-3" data-testid="add-product-form">
      <div className="flex flex-wrap items-end gap-3">
        {input("product_id", "Variant ID")}
        {input("product_name", "Name", { wide: true })}
        {input("category", "Category")}
        {input("listed_price", "Listed")}
        {input("target_price", "Target")}
        {input("minimum_price", "Minimum")}
        {input("unit_cost", "Cost")}
        {input("available_stock", "Stock")}
      </div>
      {error && <p className="text-sm text-red-600" role="alert">{error.message}</p>}
      <div className="flex gap-2">
        <button onClick={submit} className="rounded bg-sky-700 px-3 py-1 text-sm text-white" data-testid="save-product">Add</button>
        <button onClick={() => setOpen(false)} className="rounded border px-3 py-1 text-sm">Cancel</button>
      </div>
    </div>
  );
}

const margin = (price: number, cost: number) => (price > 0 ? Math.round(((price - cost) / price) * 100) : 0);

function PriceBar({ p }: { p: Product }) {
  const cost = Number(p.unit_cost);
  const listed = Number(p.listed_price);
  const min = Number(p.minimum_price);
  const target = p.target_price == null ? (listed + min) / 2 : Number(p.target_price);
  const lo = Math.min(cost, min) * 0.95;
  const pos = (v: number) => `${Math.min(98, Math.max(2, ((v - lo) / Math.max(listed - lo, 1)) * 100))}%`;
  const marks: [string, number, string][] = [["Cost", cost, "bg-slate-400"], ["Lowest", min, "bg-amber-500"], ["Aim", target, "bg-sky-500"], ["Shelf", listed, "bg-pink-600"]];
  const margins = [
    { label: "At lowest", value: margin(min, cost) },
    { label: "At your aim", value: margin(target, cost) },
    { label: "At shelf", value: margin(listed, cost) },
  ];
  return (
    <div className="space-y-4" data-testid="price-bar">
      <div className="relative mx-1 mb-2 mt-8 h-2 rounded-full bg-sky-100" aria-hidden>
        {marks.map(([label, v, tone]) => (
          <span key={label} className="absolute -top-6 -translate-x-1/2 whitespace-nowrap text-center text-[11px] font-medium leading-none text-[#415981]" style={{ left: pos(v) }}>
            {label}
            <span className={`mx-auto mt-2 block h-3.5 w-3.5 rounded-full ${tone} ring-2 ring-white`} />
          </span>
        ))}
      </div>
      <dl className="grid grid-cols-3 gap-2 border-t border-sky-100 pt-3">
        {margins.map((item) => (
          <div key={item.label}>
            <dt className="text-[11px] font-medium text-[#5b6f94]">{item.label}</dt>
            <dd className="mt-0.5 text-sm font-semibold tabular-nums text-[#071844]">{item.value}%</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function Drawer({ product, onClose, onSaved, onDelete }: { product: Product; onClose: () => void; onSaved: (p: Product) => void; onDelete: () => void }) {
  const [failed, setFailed] = useState<string | null>(null);
  async function toggle() {
    try {
      onSaved(await api.patchProduct(product.product_id, { negotiable: !product.negotiable }));
      setFailed(null);
    } catch (e) {
      setFailed(e instanceof ApiError ? e.message : "Could not save");
    }
  }
  return (
    <aside role="region" aria-label={`Edit ${product.product_name}`} className="divide-y divide-sky-100 rounded-2xl border border-sky-200 bg-white px-4 shadow-lg sm:px-5" data-testid="product-drawer">
      <header className="flex items-start justify-between gap-4 py-4">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-wide text-[#5b6f94]">{product.category}</p>
          <h3 className="mt-1 text-lg font-bold leading-6 text-[#071844]">{product.product_name}</h3>
          {Object.values(product.attributes).length > 0 && (
            <ul className="mt-2 flex flex-wrap gap-1.5" aria-label="Product options">
              {Object.values(product.attributes).map((value) => <li key={String(value)} className="rounded-full bg-sky-50 px-2.5 py-1 text-xs font-medium text-[#253d70]">{String(value)}</li>)}
            </ul>
          )}
        </div>
        <button onClick={onClose} className="grid h-10 w-10 shrink-0 place-items-center rounded-full text-[#415981] transition hover:bg-sky-50 hover:text-[#071844]" aria-label="Close details" data-testid="close-drawer">
          <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" /></svg>
        </button>
      </header>
      <section className="space-y-4 py-4" aria-labelledby={`price-title-${product.product_id}`}>
        <div>
          <h4 id={`price-title-${product.product_id}`} className="text-sm font-bold text-[#071844]">Price and margin</h4>
          <p className="mt-0.5 text-xs leading-5 text-[#5b6f94]">Your lowest price is the limit Hermion always protects.</p>
        </div>
        <PriceBar p={product} />
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          {COLUMNS.slice(0, 3).map((c) => <EditableCell key={c.field} product={product} field={c.field} label={c.label} onSaved={onSaved} />)}
        </div>
        <div className="border-t border-sky-100 pt-3">
          <h5 className="mb-2 text-xs font-semibold uppercase tracking-wide text-[#5b6f94]">Cost and inventory</h5>
          <div className="grid grid-cols-2 gap-3">
            {COLUMNS.slice(3).map((c) => <EditableCell key={c.field} product={product} field={c.field} label={c.label} onSaved={onSaved} />)}
          </div>
        </div>
        <p className="rounded-xl bg-sky-50 px-3 py-2.5 text-xs leading-5 text-[#415981]">Press Enter or leave a field to save. Keep your aim between the lowest and shelf prices; Hermion will never offer less than your lowest price.</p>
      </section>

      <section className="space-y-3 py-4">
        <label className="flex min-h-11 cursor-pointer items-center gap-3 text-sm font-medium text-[#071844]">
          <input type="checkbox" className="h-4 w-4 accent-pink-600" checked={product.negotiable} onChange={toggle} data-testid="negotiable-toggle" />
          Customers can negotiate this price
        </label>
        {failed && <p className="text-sm text-red-700" role="alert">{failed}</p>}
      </section>

      {(product.pitch || product.selling_points?.length) && (
        <section className="space-y-3 py-4">
          <h4 className="text-sm font-bold text-[#071844]">What Hermion tells customers</h4>
          {product.pitch && <p className="text-sm leading-6 text-[#253d70]">{product.pitch}</p>}
          {product.selling_points?.length ? (
            <ul className="space-y-1.5 text-sm leading-5 text-[#253d70]">
              {product.selling_points.map((point) => <li key={point} className="flex gap-2"><span aria-hidden="true" className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-pink-500" />{point}</li>)}
            </ul>
          ) : null}
          {product.best_for?.length ? <p className="text-xs leading-5 text-[#415981]">Good for: {product.best_for.join(", ")}</p> : null}
        </section>
      )}
      {product.specs && Object.keys(product.specs).length > 0 && (
        <dl className="grid grid-cols-1 gap-3 py-4 sm:grid-cols-2">
          {Object.entries(product.specs).map(([k, v]) => (
            <div key={k} className="min-w-0">
              <dt className="text-xs font-semibold text-[#5b6f94]">{k}</dt>
              <dd className="mt-0.5 break-words text-sm text-[#071844]">{String(v)}</dd>
            </div>
          ))}
        </dl>
      )}
      {product.objection_replies?.length ? (
        <section className="space-y-2 py-4 text-sm">
          <h4 className="font-semibold text-[#071844]">If a customer asks</h4>
          <ul className="space-y-2 text-sm leading-5 text-[#253d70]">{product.objection_replies.map((o) => <li key={o.objection}><strong className="text-[#071844]">“{o.objection}”</strong><span className="block mt-0.5">{o.reply}</span></li>)}</ul>
        </section>
      ) : null}
      <footer className="py-3">
        <button onClick={onDelete} className="inline-flex min-h-10 items-center gap-2 rounded-lg px-2 text-sm font-semibold text-red-700 transition hover:bg-red-50" aria-label={`Delete ${product.product_id}`}>
          <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M4 7h16M10 11v6m4-6v6M6 7l1 13h10l1-13M9 7V4h6v3" /></svg>
          Remove this product
        </button>
      </footer>
    </aside>
  );
}

export function Catalog({ products, onChange, merchantId }: { products: Product[]; onChange: (p: Product[]) => void; merchantId: string | null }) {
  const [query, setQuery] = useState("");
  const [openId, setOpenId] = useState<string | null>(null);
  const replace = (p: Product) => onChange(products.map((x) => (x.product_id === p.product_id ? p : x)));
  const shown = products.filter((p) => `${p.product_name} ${p.category} ${Object.values(p.attributes).join(" ")}`.toLowerCase().includes(query.toLowerCase()));
  const open = products.find((p) => p.product_id === openId) ?? null;

  async function remove(p: Product) {
    try {
      await api.deleteProduct(p.product_id);
      onChange(products.filter((x) => x.product_id !== p.product_id));
      setOpenId(null);
    } catch (e) {
      window.alert(e instanceof ApiError ? e.message : "Could not delete");
    }
  }

  return (
    <div className="space-y-3" data-testid="catalog">
      <Goals products={products} merchantId={merchantId} />
      <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search products" aria-label="Search products" className="w-full rounded-full border border-sky-200 bg-white px-4 py-2 text-sm" />
      <div className={`grid gap-4 ${open ? "xl:grid-cols-[1fr_24rem]" : ""}`}>
        <ul className="space-y-2">
          {shown.map((p) => (
            <li key={p.product_id}>
              <button
                onClick={() => setOpenId(p.product_id === openId ? null : p.product_id)}
                aria-expanded={p.product_id === openId}
                data-testid={`row-${p.product_id}`}
                className={`flex w-full items-center gap-3 rounded-2xl border bg-white px-4 py-3 text-left shadow-sm ${p.product_id === openId ? "border-pink-300" : "border-sky-100 hover:border-sky-300"}`}
              >
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-semibold text-[#071844]">{p.product_name}</span>
                  <span className="mt-1 flex flex-wrap gap-1">
                    {Object.values(p.attributes).map((v) => (
                      <span key={String(v)} className="rounded-full bg-sky-50 px-2 py-0.5 text-[11px] text-[#253d70]">{String(v)}</span>
                    ))}
                  </span>
                </span>
                <span className="text-sm font-semibold text-[#071844]">{rupees(p.listed_price)}</span>
                <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${p.available_stock === 0 ? "bg-red-100 text-red-700" : p.available_stock <= 3 ? "bg-amber-100 text-amber-800" : "bg-emerald-100 text-emerald-800"}`}>
                  {p.available_stock === 0 ? "Out" : `${p.available_stock} left`}
                </span>
                <span title={p.negotiable ? "Negotiable" : "Fixed price"} className={`h-2.5 w-2.5 rounded-full ${p.negotiable ? "bg-pink-500" : "bg-slate-300"}`} aria-label={p.negotiable ? "Negotiable" : "Fixed price"} />
              </button>
            </li>
          ))}
          {shown.length === 0 && <li className="px-1 text-sm text-slate-400">No products match.</li>}
        </ul>
        {open && <Drawer product={open} onClose={() => setOpenId(null)} onSaved={replace} onDelete={() => remove(open)} />}
      </div>
      <AddProduct onAdded={(p) => onChange([...products, p].sort((a, b) => a.product_id.localeCompare(b.product_id)))} />
    </div>
  );
}
