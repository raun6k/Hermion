"use client";

// Walking skeleton of the merchant console: shop + catalog count over REST, live trace over WS.
// Real tabs (Catalog, Shop, Sessions, Stats), review card and briefing come in lane M.
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { USE_MOCKS } from "@/lib/config";
import { connectMerchant } from "@/lib/ws";
import type { Health, MerchantOutbound, MerchantProfile } from "@/lib/types";

interface TraceLine {
  key: string;
  sessionId: string;
  text: string;
}

function describe(e: MerchantOutbound): string {
  switch (e.type) {
    case "session_created":
      return `session started (${e.session.state})`;
    case "session_state":
      return `state → ${e.state}`;
    case "trace":
      return e.kind === "message" ? `${String(e.data.speaker)}: ${String(e.data.text)}` : `${e.kind} update`;
    case "deal_request":
      return `basket sent for review (₹${e.basket.total})`;
  }
}

export function MerchantPane() {
  const [shop, setShop] = useState<MerchantProfile | null>(null);
  const [productCount, setProductCount] = useState<number | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [trace, setTrace] = useState<TraceLine[]>([]);

  useEffect(() => {
    if (USE_MOCKS) return;
    Promise.all([api.merchant(), api.products(), api.health().catch(() => null)])
      .then(([m, p, h]) => {
        setShop(m);
        setProductCount(p.length);
        setHealth(h);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  useEffect(() => {
    let n = 0;
    const conn = connectMerchant((e) => {
      const sessionId = "session" in e ? e.session.session_id : e.session_id;
      setTrace((t) => [...t, { key: `${n++}`, sessionId, text: describe(e) }]);
    });
    return () => conn.close();
  }, []);

  return (
    <section className="flex h-full flex-col gap-4 bg-slate-50 p-6" data-testid="merchant-pane">
      <header className="flex items-baseline justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900" data-testid="shop-name">
            {USE_MOCKS ? "Lakshmi Fashions (mock)" : (shop?.shop_name ?? "Loading shop…")}
          </h1>
          <p className="text-sm text-slate-500">
            Merchant console · {productCount ?? "–"} products in catalog
          </p>
        </div>
        {health && (
          <ul className="flex gap-2 text-xs" data-testid="health">
            {Object.entries(health.checks).map(([name, c]) => (
              <li
                key={name}
                className={`rounded px-2 py-1 ${c.status === "error" ? "bg-red-100 text-red-700" : c.status === "fake" ? "bg-amber-100 text-amber-800" : "bg-emerald-100 text-emerald-800"}`}
              >
                {name}: {c.status}
              </li>
            ))}
          </ul>
        )}
      </header>
      {error && <p className="rounded bg-red-100 p-2 text-sm text-red-700">Backend error: {error}</p>}

      <div className="flex min-h-0 flex-1 flex-col rounded-lg border border-slate-200 bg-white">
        <h2 className="border-b border-slate-200 px-4 py-2 text-sm font-medium text-slate-700">Live trace</h2>
        <ol className="flex-1 space-y-1 overflow-y-auto p-4 font-mono text-xs" data-testid="merchant-trace">
          {trace.length === 0 && <li className="text-slate-400">No activity yet.</li>}
          {trace.map((line) => (
            <li key={line.key}>
              <span className="text-slate-400">#{line.sessionId.slice(0, 8)}</span> {line.text}
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
