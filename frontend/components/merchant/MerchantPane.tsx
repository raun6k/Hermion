"use client";

// Merchant console (docs/frontend.md): Customers, Approvals, Products, Shop, Insights tabs. Baskets and price checks
// waiting for the merchant live only on the Approvals tab. Talks to the backend only through lib/api and lib/ws.
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, setMerchantId } from "@/lib/api";
import { USE_MOCKS } from "@/lib/config";
import { COPY } from "@/lib/copy";
import { merchantAddress } from "@/lib/format";
import { connectMerchant } from "@/lib/ws";
import type { MerchantChoice, MerchantProfile, Product, SessionSummary } from "@/lib/types";
import { AvatarMenu } from "./AvatarMenu";
import { Catalog } from "./Catalog";
import { PriceCheckCard } from "./PriceCheckCard";
import { ReviewCard } from "./ReviewCard";
import { Sessions } from "./Sessions";
import { Shop } from "./Shop";
import { Stats } from "./Stats";

type Tab = "review" | "catalog" | "shop" | "sessions" | "stats";
const TABS: { id: Tab; label: string }[] = [
  { id: "sessions", label: COPY.tabs.sessions },
  { id: "review", label: COPY.tabs.review },
  { id: "catalog", label: COPY.tabs.catalog },
  { id: "shop", label: COPY.tabs.shop },
  { id: "stats", label: COPY.tabs.stats },
];
const SHOP_KEY = "hermion.merchant";
const REVIEW_STATES = ["pending_merchant", "briefing", "in_person"];

export function MerchantPane() {
  const [tab, setTab] = useState<Tab>("sessions");
  const [shop, setShop] = useState<MerchantProfile | null>(null);
  const [products, setProducts] = useState<Product[]>([]);
  const [shops, setShops] = useState<MerchantChoice[]>([]);
  const [shopId, setShopId] = useState<string | null>(() => {
    try {
      const saved = typeof localStorage === "undefined" ? null : localStorage.getItem(SHOP_KEY);
      setMerchantId(saved);
      return saved;
    } catch {
      return null;
    }
  });
  const [error, setError] = useState<string | null>(null);
  const [sessions, setSessions] = useState<Record<string, SessionSummary>>({});
  const [versions, setVersions] = useState<Record<string, number>>({});
  const [selected, setSelected] = useState<string | null>(null);
  const [statsVersion, setStatsVersion] = useState(0);

  const bump = useCallback((id: string) => setVersions((v) => ({ ...v, [id]: (v[id] ?? 0) + 1 })), []);

  useEffect(() => {
    api.merchants().then(setShops).catch(() => {});
  }, []);

  useEffect(() => {
    Promise.all([api.merchant(), api.products(), api.sessions("live"), api.sessions("past")])
      .then(([m, p, live, past]) => {
        setShop(m);
        setShopId(m.merchant_id);
        setProducts(p);
        setSessions(Object.fromEntries([...live, ...past].map((s) => [s.session_id, s])));
        setError(null);
      })
      .catch((e: Error) => setError(e.message));
  }, [shopId]);

  function switchShop(id: string) {
    setMerchantId(id);
    try {
      localStorage.setItem(SHOP_KEY, id);
    } catch {}
    setShop(null);
    setSessions({});
    setSelected(null);
    setShopId(id);
    setStatsVersion((n) => n + 1);
  }

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
        if (e.type === "trace" && e.kind === "timing") setStatsVersion((n) => n + 1);
        if (e.type === "deal_request" || (e.type === "trace" && e.kind === "basket"))
          api.sessions("live").then((live) => setSessions((s) => ({ ...s, ...Object.fromEntries(live.map((x) => [x.session_id, x])) }))).catch(() => {});
      }
    }, shopId);
    return () => conn.close();
  }, [bump, shopId]);

  const list = useMemo(() => Object.values(sessions).sort((a, b) => b.started_at.localeCompare(a.started_at)), [sessions]);
  const checks = list.filter((s) => s.price_check);
  const reviews = list.filter((s) => REVIEW_STATES.includes(s.state));
  const waiting = checks.length + reviews.length;
  const headerAddress = shop ? merchantAddress(shop.shop_description) : "";

  function openTrace(id: string) {
    setSelected(id);
    setTab("sessions");
  }

  return (
    <section className="relative flex min-h-[760px] flex-col gap-4 overflow-hidden rounded-[26px] bg-[#dff4fc] p-5 text-[#081b4d] sm:p-6 lg:h-full lg:min-h-0" data-testid="merchant-pane">
      <header className="sticky top-0 z-10 -mx-1 flex items-center justify-between gap-3 rounded-2xl bg-[#dff4fc]/95 px-1 pb-3 backdrop-blur">
        <div className="flex min-w-0 items-center gap-4">
          <span className="flex shrink-0 items-center gap-1.5 text-xl font-bold tracking-tight text-[#071844]"><svg aria-hidden viewBox="0 0 24 24" className="h-6 w-6 fill-pink-600"><path d="M12 1c1.1 6.2 3.8 8.9 11 11-7.2 2.1-9.9 4.8-11 11C10.9 16.8 8.2 14.1 1 12 8.2 9.9 10.9 7.2 12 1Z" /></svg>Hermion</span>
          <span className="h-8 w-px shrink-0 bg-sky-200" aria-hidden />
          <div className="min-w-0">
            <h1 className="truncate text-base font-bold leading-tight text-[#071844]" data-testid="shop-name">
              {shop?.shop_name ?? "Loading shop…"}
              {USE_MOCKS && <span className="ml-2 rounded-full bg-amber-100 px-2 py-0.5 align-middle text-[10px] font-semibold text-amber-800">sample data</span>}
            </h1>
            {headerAddress && <p className="truncate text-xs text-[#415981]" data-testid="shop-address">{headerAddress}</p>}
          </div>
        </div>
        <div className="flex items-center gap-3">
          <AvatarMenu shops={shops} current={shopId} onSwitch={switchShop} />
        </div>
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
            {t.id === "review" && waiting > 0 && (
              <span className="ml-1.5 rounded-full bg-pink-500 px-1.5 text-xs text-white" data-testid="review-badge">
                {waiting}
                <span className="sr-only"> waiting</span>
              </span>
            )}
          </button>
        ))}
      </nav>

      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto pb-4 pr-1">
        {tab === "catalog" && <Catalog products={products} onChange={setProducts} merchantId={shop?.merchant_id ?? shopId} />}
        {tab === "shop" && shop && <Shop shop={shop} onSaved={setShop} />}
        {tab === "sessions" && (
          <Sessions sessions={list} versions={versions} products={products} selected={selected} onSelect={setSelected} />
        )}
        {tab === "stats" && <Stats version={statsVersion} />}

        {tab === "review" && (
          <section className="space-y-4" id="review-dock" data-testid="review-dock" aria-labelledby="review-title">
            <h2 id="review-title" className="text-lg font-bold text-[#071844]">{COPY.review.title}</h2>
            {waiting === 0 && (
              <p className="rounded-2xl border border-dashed border-sky-300 bg-white/60 p-6 text-center text-sm text-[#415981]" data-testid="review-empty">
                {COPY.review.empty}
              </p>
            )}
            {checks.map((s) => (
              <PriceCheckCard
                key={`check-${s.session_id}`}
                sessionId={s.session_id}
                customer={s.display_name || "A customer"}
                check={s.price_check!}
                products={products}
                onAnswered={() => {
                  bump(s.session_id);
                  api.sessions("live").then((live) => setSessions((cur) => ({ ...cur, ...Object.fromEntries(live.map((x) => [x.session_id, x])) }))).catch(() => {});
                }}
              />
            ))}
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
          </section>
        )}
      </div>
      <p className="sr-only" aria-live="polite">{waiting ? COPY.review.waiting(waiting) : ""}</p>
    </section>
  );
}
