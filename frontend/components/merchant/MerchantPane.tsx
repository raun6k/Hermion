"use client";

// Merchant console (docs/frontend.md): Catalog, Shop, Sessions, Stats tabs; review cards pinned under
// the tabs; the shop QR pinned bottom-right. Talks to the backend only through lib/api and lib/ws.
import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { USE_MOCKS } from "@/lib/config";
import { shortId } from "@/lib/format";
import { connectMerchant } from "@/lib/ws";
import type { Health, MerchantProfile, Product, SessionSummary } from "@/lib/types";
import { Catalog } from "./Catalog";
import { ReviewCard } from "./ReviewCard";
import { Sessions } from "./Sessions";
import { Shop } from "./Shop";
import { ShopQR } from "./ShopQR";
import { Stats } from "./Stats";

type Tab = "catalog" | "shop" | "sessions" | "stats";
const TABS: { id: Tab; label: string }[] = [
  { id: "catalog", label: "Catalog" },
  { id: "shop", label: "Shop" },
  { id: "sessions", label: "Sessions" },
  { id: "stats", label: "Stats" },
];
const REVIEW_STATES = ["pending_merchant", "briefing", "in_person"];

export function MerchantPane() {
  const [tab, setTab] = useState<Tab>("sessions");
  const [shop, setShop] = useState<MerchantProfile | null>(null);
  const [products, setProducts] = useState<Product[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sessions, setSessions] = useState<Record<string, SessionSummary>>({});
  const [versions, setVersions] = useState<Record<string, number>>({});
  const [selected, setSelected] = useState<string | null>(null);
  const [statsVersion, setStatsVersion] = useState(0);

  const bump = useCallback((id: string) => setVersions((v) => ({ ...v, [id]: (v[id] ?? 0) + 1 })), []);

  useEffect(() => {
    Promise.all([api.merchant(), api.products(), api.health().catch(() => null), api.sessions("live"), api.sessions("past")])
      .then(([m, p, h, live, past]) => {
        setShop(m);
        setProducts(p);
        setHealth(h);
        setSessions(Object.fromEntries([...live, ...past].map((s) => [s.session_id, s])));
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  useEffect(() => {
    const conn = connectMerchant((e) => {
      if (e.type === "session_created") {
        setSessions((s) => ({ ...s, [e.session.session_id]: e.session }));
        setSelected((cur) => cur ?? e.session.session_id);
      } else if (e.type === "session_state") {
        setSessions((s) => (s[e.session_id] ? { ...s, [e.session_id]: { ...s[e.session_id], state: e.state } } : s));
        bump(e.session_id);
        setStatsVersion((n) => n + 1);
        // Stock may have changed on accept; refresh the catalog quietly.
        if (e.state === "accepted") api.products().then(setProducts).catch(() => {});
      } else {
        bump(e.session_id);
        if (e.type === "deal_request" || (e.type === "trace" && e.kind === "basket"))
          api.sessions("live").then((live) => setSessions((s) => ({ ...s, ...Object.fromEntries(live.map((x) => [x.session_id, x])) }))).catch(() => {});
      }
    });
    return () => conn.close();
  }, [bump]);

  const list = useMemo(() => Object.values(sessions).sort((a, b) => b.started_at.localeCompare(a.started_at)), [sessions]);
  const reviews = list.filter((s) => REVIEW_STATES.includes(s.state));

  function openTrace(id: string) {
    setSelected(id);
    setTab("sessions");
  }

  return (
    <section className="relative flex h-full flex-col gap-3 overflow-hidden rounded-3xl bg-sky-50 p-6" data-testid="merchant-pane">
      <header className="flex items-baseline justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900" data-testid="shop-name">
            {shop?.shop_name ?? "Loading shop…"}
            {USE_MOCKS && <span className="ml-2 rounded bg-amber-100 px-2 py-0.5 align-middle text-xs font-normal text-amber-800">mock data</span>}
          </h1>
          <p className="text-sm text-slate-500">Merchant console · {products.length ? `${products.length} products in catalog` : "– products in catalog"}</p>
        </div>
        {health && (
          <ul className="flex gap-2 text-xs" data-testid="health">
            {Object.entries(health.checks).map(([name, c]) => (
              <li key={name} className={`rounded px-2 py-1 ${c.status === "error" ? "bg-red-100 text-red-700" : c.status === "fake" ? "bg-amber-100 text-amber-800" : "bg-emerald-100 text-emerald-800"}`}>
                {name}: {c.status}
              </li>
            ))}
          </ul>
        )}
      </header>
      {error && <p className="rounded bg-red-100 p-2 text-sm text-red-700">Backend error: {error}</p>}

      <nav className="flex gap-1 border-b border-slate-200" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={tab === t.id}
            onClick={() => setTab(t.id)}
            className={`-mb-px border-b-2 px-4 py-2 text-sm font-medium ${tab === t.id ? "border-pink-500 text-slate-900" : "border-transparent text-slate-500 hover:text-slate-800"}`}
            data-testid={`tab-${t.id}`}
          >
            {t.label}
            {t.id === "sessions" && reviews.length > 0 && (
              <span className="ml-1.5 rounded-full bg-pink-500 px-1.5 text-xs text-white" data-testid="review-badge">{reviews.length}</span>
            )}
          </button>
        ))}
      </nav>

      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto pb-40 pr-1">
        {tab === "catalog" && <Catalog products={products} onChange={setProducts} />}
        {tab === "shop" && shop && <Shop shop={shop} onSaved={setShop} products={products} />}
        {tab === "sessions" && (
          <Sessions sessions={list} versions={versions} products={products} selected={selected} onSelect={setSelected} />
        )}
        {tab === "stats" && <Stats version={statsVersion} />}

        {reviews.length > 0 && (
          <div className="space-y-3" data-testid="review-dock">
            {reviews.map((s) => (
              <ReviewCard
                key={s.session_id}
                sessionId={s.session_id}
                version={versions[s.session_id] ?? 0}
                products={products}
                onOpenTrace={openTrace}
                onChanged={() => {
                  bump(s.session_id);
                  api.sessions("live").then((live) => setSessions((cur) => ({ ...cur, ...Object.fromEntries(live.map((x) => [x.session_id, x])) }))).catch(() => {});
                }}
              />
            ))}
          </div>
        )}
      </div>
      <p className="sr-only" aria-live="polite">{reviews.length ? `Basket for review ${shortId(reviews[0].session_id)}` : ""}</p>
      <ShopQR token={shop?.qr_token ?? null} />
    </section>
  );
}
