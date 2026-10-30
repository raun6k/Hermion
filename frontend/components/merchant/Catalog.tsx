"use client";

import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { rupees } from "@/lib/format";
import type { Product, ProductCreate } from "@/lib/types";

type NumField = "listed_price" | "target_price" | "minimum_price" | "unit_cost" | "available_stock";
const COLUMNS: { field: NumField; label: string; hint?: string }[] = [
  { field: "listed_price", label: "Listed" },
  { field: "target_price", label: "Target", hint: "blank = midpoint" },
  { field: "minimum_price", label: "Minimum" },
  { field: "unit_cost", label: "Cost" },
  { field: "available_stock", label: "Stock" },
];

function EditableCell({
  product,
  field,
  onSaved,
}: {
  product: Product;
  field: NumField;
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
    <td className="px-2 py-1 align-top">
      <input
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
        className={`w-20 rounded border px-1.5 py-0.5 text-right text-sm tabular-nums ${error ? "border-red-400 bg-red-50" : "border-transparent hover:border-slate-300 focus:border-sky-400"}`}
      />
      {error && (
        <p className="mt-0.5 max-w-36 text-[11px] leading-tight text-red-600" role="alert" data-testid={`error-${product.product_id}-${field}`}>
          {error}
        </p>
      )}
    </td>
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

export function Catalog({ products, onChange }: { products: Product[]; onChange: (p: Product[]) => void }) {
  const replace = (p: Product) => onChange(products.map((x) => (x.product_id === p.product_id ? p : x)));

  async function toggleNegotiable(p: Product) {
    replace(await api.patchProduct(p.product_id, { negotiable: !p.negotiable }));
  }
  async function remove(p: Product) {
    try {
      await api.deleteProduct(p.product_id);
      onChange(products.filter((x) => x.product_id !== p.product_id));
    } catch (e) {
      window.alert(e instanceof ApiError ? e.message : "Could not delete");
    }
  }

  return (
    <div className="space-y-3" data-testid="catalog">
      <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-3 py-2">Variant</th>
              {COLUMNS.map((c) => (
                <th key={c.field} className="px-2 py-2 text-right" title={c.hint}>{c.label}</th>
              ))}
              <th className="px-2 py-2">Negotiable</th>
              <th />
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {products.map((p) => (
              <tr key={p.product_id} data-testid={`row-${p.product_id}`} className={p.available_stock === 0 ? "bg-slate-50 text-slate-500" : ""}>
                <td className="px-3 py-1.5">
                  <div className="font-medium text-slate-800">{p.product_name}</div>
                  <div className="text-xs text-slate-500">
                    {p.product_id} · {Object.values(p.attributes).join(" · ")}
                  </div>
                </td>
                {COLUMNS.map((c) => (
                  <EditableCell key={c.field} product={p} field={c.field} onSaved={replace} />
                ))}
                <td className="px-2 py-1.5">
                  <button
                    onClick={() => toggleNegotiable(p)}
                    className={`rounded-full px-2 py-0.5 text-xs ${p.negotiable ? "bg-emerald-100 text-emerald-800" : "bg-slate-200 text-slate-700"}`}
                    aria-pressed={p.negotiable}
                  >
                    {p.negotiable ? "negotiable" : `fixed ${rupees(p.listed_price)}`}
                  </button>
                </td>
                <td className="px-2">
                  <button onClick={() => remove(p)} className="text-xs text-slate-400 hover:text-red-600" aria-label={`Delete ${p.product_id}`}>
                    ✕
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-slate-500">Edit a cell and press Enter. Rule: 0 &lt; minimum ≤ target ≤ listed, whole rupees. Hermion never sells below the minimum.</p>
      <AddProduct onAdded={(p) => onChange([...products, p].sort((a, b) => a.product_id.localeCompare(b.product_id)))} />
    </div>
  );
}
