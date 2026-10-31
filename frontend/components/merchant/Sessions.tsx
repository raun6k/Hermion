"use client";

import { useState } from "react";
import { languageName, rupees, STATE_LABEL, when } from "@/lib/format";
import type { Product, SessionSummary } from "@/lib/types";
import { TraceView } from "./TraceView";

const TERMINAL = ["accepted", "declined", "exited"];
const PROGRESS: Record<string, number> = { intro: 8, discovery: 25, negotiating: 55, pending_merchant: 80, briefing: 80, in_person: 90, accepted: 100, declined: 100, exited: 100 };
const STATE_PILL: Record<string, string> = {
  accepted: "bg-emerald-100 text-emerald-800",
  declined: "bg-red-100 text-red-700",
  exited: "bg-slate-100 text-slate-600",
  pending_merchant: "bg-pink-100 text-pink-700",
  briefing: "bg-violet-100 text-violet-800",
  in_person: "bg-violet-100 text-violet-800",
};

export function Sessions({
  sessions,
  versions,
  products,
  selected,
  onSelect,
}: {
  sessions: SessionSummary[];
  versions: Record<string, number>;
  products: Product[];
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  const [scope, setScope] = useState<"live" | "past">("live");
  const shown = sessions.filter((s) => TERMINAL.includes(s.state) === (scope === "past"));
  const live = sessions.filter((s) => !TERMINAL.includes(s.state)).length;
  const past = sessions.length - live;

  return (
    <div className="grid min-h-[28rem] shrink-0 grid-cols-1 grid-rows-[auto_minmax(16rem,1fr)] gap-4 md:grid-cols-[minmax(175px,240px)_1fr] md:grid-rows-1" data-testid="sessions">
      <div className="min-h-0 space-y-2 overflow-y-auto">
        <div className="flex rounded-full bg-white p-1 text-sm shadow-sm ring-1 ring-sky-100" role="group" aria-label="Which customers">
          {(["live", "past"] as const).map((s) => (
            <button
              key={s}
              onClick={() => setScope(s)}
              aria-pressed={scope === s}
              className={`flex min-h-9 flex-1 items-center justify-center gap-1.5 rounded-full px-3 font-semibold transition ${scope === s ? "bg-[#071f5c] text-white" : "text-[#415981] hover:text-[#071844]"}`}
              data-testid={`scope-${s}`}
            >
              {s === "live" && <span className={`h-2 w-2 rounded-full ${live ? "bg-emerald-400" : "bg-slate-300"}`} aria-hidden />}
              {s === "live" ? "Now" : "Earlier"}
              <span className={`rounded-full px-1.5 text-xs ${scope === s ? "bg-white/20" : "bg-sky-50"}`}>{s === "live" ? live : past}</span>
            </button>
          ))}
        </div>
        <ul className="space-y-2" data-testid="session-list">
          {shown.length === 0 && <li className="rounded-2xl border border-dashed border-sky-200 px-3 py-4 text-center text-sm text-[#415981]">{scope === "live" ? "No one is talking to Hermion right now." : "No earlier customers yet."}</li>}
          {shown.map((s) => (
            <li key={s.session_id}>
              <button
                onClick={() => onSelect(s.session_id)}
                aria-current={selected === s.session_id || undefined}
                className={`w-full rounded-2xl border bg-white p-3 text-left shadow-sm transition ${selected === s.session_id ? "border-pink-300 ring-2 ring-pink-100" : "border-sky-100 hover:-translate-y-px hover:border-sky-300 hover:shadow"}`}
                data-testid="session-row"
                data-state={s.state}
              >
                <div className="flex items-start justify-between gap-2">
                  <span className="flex min-w-0 items-center gap-2">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-sky-100 text-xs font-bold text-[#071f5c]" aria-hidden>{(s.display_name || "C").slice(0, 1)}</span>
                    <span className="truncate text-sm font-semibold text-[#071844]">{s.display_name || "Customer"}</span>
                  </span>
                  <span className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-semibold ${STATE_PILL[s.state] ?? "bg-slate-100 text-slate-600"}`}>{STATE_LABEL[s.state] ?? s.state}</span>
                </div>
                <div className="mt-1 pl-9 text-xs text-[#415981]">{when(s.started_at)}{s.language ? ` · ${languageName(s.language)}` : ""}</div>
                <div className="mt-2 flex items-center gap-2">
                  <div className="h-1.5 flex-1 rounded-full bg-sky-100" aria-hidden>
                    <div className="h-1.5 rounded-full bg-pink-500" style={{ width: `${PROGRESS[s.state] ?? 10}%` }} />
                  </div>
                  <span className="text-xs font-semibold text-[#071844]">{s.basket_total ? `${rupees(s.basket_total)} · ${s.line_count} item${s.line_count === 1 ? "" : "s"}` : "No basket yet"}</span>
                </div>
              </button>
            </li>
          ))}
        </ul>
      </div>
      <div className="min-h-0 overflow-y-auto rounded-2xl bg-white">
        {selected ? (
          <TraceView sessionId={selected} version={versions[selected] ?? 0} products={products} />
        ) : (
          <div className="flex h-full min-h-64 flex-col items-center justify-center px-8 text-center">
            <div className="mb-5 flex h-16 w-16 items-center justify-center rounded-full bg-sky-100 text-pink-600" aria-hidden>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className="h-8 w-8"><path d="M5 8h14l1 12H4L5 8Z"/><path d="M9 8V6a3 3 0 0 1 6 0v2"/></svg>
            </div>
            <h2 className="text-xl font-bold text-[#071844]">Your shop is ready</h2>
            <p className="mt-2 max-w-xs text-sm leading-6 text-[#415981]">Pick a customer to follow their conversation with Hermion. Baskets that need your decision go to Approvals.</p>
          </div>
        )}
      </div>
    </div>
  );
}
