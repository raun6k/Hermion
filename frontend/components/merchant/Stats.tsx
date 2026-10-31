"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { COPY, duration, responseTime } from "@/lib/copy";
import { rupees } from "@/lib/format";
import type { Stats as StatsData } from "@/lib/types";

const RANGES = [7, 30] as const;
const PALETTE = ["#db2777", "#071f5c", "#0ea5e9", "#f59e0b", "#10b981", "#8b5cf6"];

function Card({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-2xl border border-sky-100 bg-white p-4">
      <dt className="text-xs text-[#415981]">{label}</dt>
      <dd className="mt-1 text-2xl font-semibold text-[#071844]">{value}</dd>
      {hint && <p className="mt-0.5 text-xs text-[#415981]">{hint}</p>}
    </div>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-2xl border border-sky-100 bg-white p-4">
      <h3 className="mb-3 text-sm font-semibold text-[#071844]">{title}</h3>
      {children}
    </section>
  );
}

function RevenueLine({ points }: { points: { day: string; revenue: string }[] }) {
  if (points.length < 2) return <p className="text-sm text-slate-400">Not enough days yet.</p>;
  const values = points.map((p) => Number(p.revenue));
  const max = Math.max(...values, 1);
  const x = (i: number) => 8 + (i / (points.length - 1)) * 284;
  const y = (v: number) => 92 - (v / max) * 80;
  const line = values.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)} ${y(v).toFixed(1)}`).join(" ");
  return (
    <figure>
      <svg viewBox="0 0 300 100" className="h-32 w-full" role="img" aria-label={`Revenue by day, highest ${rupees(max)}`}>
        <path d={`${line} L${x(values.length - 1)} 96 L${x(0)} 96 Z`} fill="#db277722" />
        <path d={line} fill="none" stroke="#db2777" strokeWidth="2" strokeLinejoin="round" />
      </svg>
      <figcaption className="flex justify-between text-xs text-[#415981]"><span>{points[0].day.slice(5)}</span><span>{points[points.length - 1].day.slice(5)}</span></figcaption>
    </figure>
  );
}

function Bars({ rows }: { rows: { label: string; value: number; text: string }[] }) {
  const max = Math.max(...rows.map((r) => r.value), 1);
  if (!rows.length) return <p className="text-sm text-slate-400">Nothing yet.</p>;
  return (
    <ul className="space-y-2">
      {rows.map((r, i) => (
        <li key={r.label} className="text-xs">
          <div className="flex justify-between text-[#071844]"><span className="truncate pr-2">{r.label}</span><span className="font-semibold">{r.text}</span></div>
          <div className="mt-1 h-2 rounded-full bg-sky-100" aria-hidden><div className="h-2 rounded-full" style={{ width: `${(r.value / max) * 100}%`, background: PALETTE[i % PALETTE.length] }} /></div>
        </li>
      ))}
    </ul>
  );
}

function Donut({ rows, label, colors = PALETTE, empty = "Nothing yet." }: { rows: { name: string; value: number }[]; label: string; colors?: string[]; empty?: string }) {
  const total = rows.reduce((a, r) => a + r.value, 0);
  if (!total) return <p className="text-sm text-slate-400">{empty}</p>;
  const offsets = rows.map((_, i) => rows.slice(0, i).reduce((a, r) => a + (r.value / total) * 100, 0));
  const radius = 15.9;
  return (
    <div className="flex items-center gap-4">
      <svg viewBox="0 0 36 36" className="h-28 w-28 shrink-0 -rotate-90" role="img" aria-label={`${label}: ${rows.map((r) => `${r.name} ${Math.round((r.value / total) * 100)}%`).join(", ")}`}>
        {rows.map((r, i) => {
          const share = (r.value / total) * 100;
          return <circle key={r.name} r={radius} cx="18" cy="18" fill="none" stroke={colors[i % colors.length]} strokeWidth="5" strokeDasharray={`${share} ${100 - share}`} strokeDashoffset={-offsets[i]} />;
        })}
      </svg>
      <ul className="space-y-1 text-xs text-[#071844]">
        {rows.slice(0, 6).map((r, i) => (
          <li key={r.name} className="flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: colors[i % colors.length] }} aria-hidden />{r.name} · {r.value} ({Math.round((r.value / total) * 100)}%)</li>
        ))}
      </ul>
    </div>
  );
}

const OUTCOME: Record<string, { label: string; color: string }> = {
  accepted: { label: "Sold", color: "#10b981" },
  declined: { label: "You declined", color: "#f59e0b" },
  exited: { label: "Left without buying", color: "#94a3b8" },
  open: { label: "Still talking", color: "#0ea5e9" },
};

/** Customers by hour of the day, in the browser's local time (the API counts in UTC). */
function Hours({ rows }: { rows: { name: string; value: number }[] }) {
  const local = new Array(24).fill(0) as number[];
  for (const r of rows) local[new Date(Date.UTC(2026, 0, 1, Number(r.name))).getHours()] += r.value;
  const max = Math.max(...local, 1);
  if (!rows.length) return <p className="text-sm text-slate-400">Nothing yet.</p>;
  const busiest = local.indexOf(max);
  const label = (h: number) => `${h % 12 || 12}${h < 12 ? "am" : "pm"}`;
  return (
    <figure>
      <div className="flex h-28 items-end gap-[3px]" role="img" aria-label={`Customers by hour; busiest around ${label(busiest)}`}>
        {local.map((v, h) => (
          <div key={h} className="flex-1 rounded-t" style={{ height: `${Math.max((v / max) * 100, v ? 6 : 2)}%`, background: h === busiest ? "#db2777" : v ? "#071f5c" : "#e0f2fe" }} title={`${label(h)}: ${v}`} />
        ))}
      </div>
      <figcaption className="mt-1 flex justify-between text-xs text-[#415981]">
        <span>12am</span><span>6am</span><span>12pm</span><span>6pm</span><span>11pm</span>
      </figcaption>
      <p className="mt-2 text-xs text-[#253d70]">Busiest around <strong>{label(busiest)}</strong>.</p>
    </figure>
  );
}

function Funnel({ f }: { f: NonNullable<StatsData["funnel"]> }) {
  const steps: [string, number][] = [["Scanned", f.scanned], ["Started", f.started], ["Got an offer", f.offered], ["In basket", f.in_basket], ["Sent to you", f.confirmed], ["Accepted", f.accepted]];
  return <Bars rows={steps.map(([label, value]) => ({ label, value, text: String(value) }))} />;
}

export function Stats({ version }: { version: number }) {
  const [days, setDays] = useState<number>(30);
  const [stats, setStats] = useState<StatsData | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let live = true;
    api.stats(days).then((s) => { if (live) { setStats(s); setError(false); } }).catch(() => live && setError(true));
    return () => {
      live = false;
    };
  }, [version, days]);

  if (error) return <p role="alert" className="text-sm text-red-700">Could not load insights. Reopen this tab to retry.</p>;
  if (!stats) return <p className="text-sm text-slate-400">Loading…</p>;
  const pct = (v?: string) => `${Math.round(Number(v ?? 0) * 100)}%`;
  return (
    <div className="space-y-4" data-testid="stats">
      <div className="flex gap-1 text-sm" role="group" aria-label="Date range">
        {RANGES.map((r) => (
          <button key={r} onClick={() => setDays(r)} aria-pressed={days === r} className={`rounded-full px-3 py-1 ${days === r ? "bg-[#071f5c] text-white" : "bg-white text-slate-600 ring-1 ring-sky-200"}`}>Last {r} days</button>
        ))}
      </div>
      <dl className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        <Card label={COPY.stats.revenue} value={rupees(stats.revenue_won)} hint={`${stats.deals} deals`} />
        <Card label={COPY.stats.discount} value={rupees(stats.discount_given)} hint={`${COPY.stats.avgDiscount} ${Number(stats.avg_discount_pct).toFixed(1)}%`} />
        <Card label={COPY.stats.negotiationTime} value={duration(stats.total_negotiation_seconds ?? 0)} hint="average per customer" />
        <Card label={COPY.stats.responseTime} value={responseTime(stats.avg_response_ms)} hint={stats.avg_response_ms == null ? "No measured replies yet" : "Hermion's reply"} />
        <Card label="Profit earned" value={rupees(stats.total_contribution)} hint="after the cost of goods" />
        <Card label="Average sale" value={rupees(stats.deals ? Math.round(Number(stats.revenue_won ?? 0) / stats.deals) : 0)} hint="per accepted basket" />
        <Card label="Customers" value={String(stats.sessions)} hint={`${stats.offers} offers made`} />
        <Card label="Sale rate" value={pct(String(stats.sessions ? stats.deals / stats.sessions : 0))} hint="customers who bought" />
        <Card label="Add-on success" value={pct(stats.upsell_attach_rate)} hint="deals with a suggested extra" />
        <Card label="Abandoned baskets" value={String(stats.abandoned_baskets ?? 0)} />
        <Card label="Asked you to step in" value={pct(stats.escalation_rate)} hint="of customers" />
      </dl>
      <div className="grid gap-3 lg:grid-cols-2">
        <Panel title="Revenue by day"><RevenueLine points={stats.per_day ?? []} /></Panel>
        <Panel title="From scan to sale">{stats.funnel && <Funnel f={stats.funnel} />}</Panel>
        <Panel title="Top products"><Bars rows={(stats.top_products ?? []).map((p) => ({ label: p.product_name, value: Number(p.revenue), text: rupees(p.revenue) }))} /></Panel>
        <Panel title="Languages customers use"><Donut rows={stats.language_mix ?? []} label="Languages customers use" empty="No language data yet." /></Panel>
        <Panel title="How conversations ended">
          <Donut
            rows={(stats.outcomes ?? []).filter((o) => o.value).map((o) => ({ name: OUTCOME[o.name]?.label ?? o.name, value: o.value }))}
            colors={(stats.outcomes ?? []).filter((o) => o.value).map((o) => OUTCOME[o.name]?.color ?? "#94a3b8")}
            label="How conversations ended"
          />
        </Panel>
        <Panel title="When customers come in"><Hours rows={stats.per_hour_utc ?? []} /></Panel>
      </div>
    </div>
  );
}
