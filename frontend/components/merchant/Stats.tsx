"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { rupees } from "@/lib/format";
import type { Stats as StatsData } from "@/lib/types";

export function Stats({ version }: { version: number }) {
  const [stats, setStats] = useState<StatsData | null>(null);
  const [unavailable, setUnavailable] = useState(false);

  useEffect(() => {
    let live = true;
    api.stats().then((s) => live && setStats(s)).catch((e) => live && setUnavailable(e instanceof ApiError && e.code === "NOT_IMPLEMENTED"));
    return () => {
      live = false;
    };
  }, [version]);

  if (unavailable) return <p className="text-sm text-slate-500">Stats arrive with the next backend stage.</p>;
  if (!stats) return <p className="text-sm text-slate-400">Loading…</p>;
  const cards: [string, string][] = [
    ["Sessions", String(stats.sessions)],
    ["Offers", String(stats.offers)],
    ["Deals", String(stats.deals)],
    ["Avg discount", `${Number(stats.avg_discount_pct).toFixed(1)}%`],
    ["Contribution", rupees(stats.total_contribution)],
  ];
  return (
    <dl className="grid grid-cols-5 gap-3" data-testid="stats">
      {cards.map(([label, value]) => (
        <div key={label} className="rounded-lg border border-slate-200 bg-white p-4">
          <dt className="text-xs text-slate-500">{label}</dt>
          <dd className="mt-1 text-2xl font-semibold text-slate-900">{value}</dd>
        </div>
      ))}
    </dl>
  );
}
