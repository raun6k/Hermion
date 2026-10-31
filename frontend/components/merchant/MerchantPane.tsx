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
    <section className="relative flex min-h-[760px] flex-col gap-4 overflow-hidden rounded-[26px] bg-[#dff4fc] p-5 text-[#081b4d] sm:p-6 lg:h-full lg:min-h-0" data-testid="merchant-pane">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-sky-200/80 pb-4">
        <div>
          <div className="flex items-center gap-2 text-3xl font-bold tracking-tight text-[#071844]"><svg aria-hidden viewBox="0 0 24 24" className="h-7 w-7 fill-pink-600"><path d="M12 1c1.1 6.2 3.8 8.9 11 11-7.2 2.1-9.9 4.8-11 11C10.9 16.8 8.2 14.1 1 12 8.2 9.9 10.9 7.2 12 1Z" /></svg>Hermion</div>
          <h1 className="pl-8 text-sm font-medium text-[#253d70]" data-testid="shop-name">
            {shop?.shop_name ?? "Loading shop…"}
            {USE_MOCKS && <span className="ml-2 rounded bg-amber-100 px-2 py-0.5 align-middle text-xs font-normal text-amber-800">mock data</span>}
          </h1>
          <p className="pl-8 text-xs text-[#415981]">Merchant console · {products.length ? `${products.length} products in catalog` : "– products in catalog"}</p>
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

      <nav className="flex gap-2 overflow-x-auto border-b border-sky-200/80" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={tab === t.id}
            onClick={() => setTab(t.id)}
            className={`-mb-px border-b-2 whitespace-nowrap px-4 py-3 text-sm font-semibold ${tab === t.id ? "border-pink-600 text-pink-700" : "border-transparent text-[#344b75] hover:text-[#071844]"}`}
            data-testid={`tab-${t.id}`}
          >
            {t.label}
            {t.id === "sessions" && reviews.length > 0 && (
              <span className="ml-1.5 rounded-full bg-pink-500 px-1.5 text-xs text-white" data-testid="review-badge">{reviews.length}</span>
            )}
          </button>
        ))}
      </nav>

      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto pb-4 pr-1">
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
