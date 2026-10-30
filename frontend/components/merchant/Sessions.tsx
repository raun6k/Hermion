"use client";

import { useState } from "react";
import { hhmm, rupees, shortId, STATE_LABEL } from "@/lib/format";
import type { Product, SessionSummary } from "@/lib/types";
import { TraceView } from "./TraceView";

const TERMINAL = ["accepted", "declined", "exited"];

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
    <div className="grid h-[24rem] shrink-0 grid-cols-[260px_1fr] gap-4" data-testid="sessions">
      <div className="min-h-0 space-y-2 overflow-y-auto">
        <div className="flex gap-1 text-sm">
          {(["live", "past"] as const).map((s) => (
            <button
              key={s}
              onClick={() => setScope(s)}
              className={`rounded-full px-3 py-1 ${scope === s ? "bg-sky-700 text-white" : "bg-white text-slate-600 ring-1 ring-sky-200"}`}
              data-testid={`scope-${s}`}
            >
              {s === "live" ? `● live (${live})` : `○ past (${past})`}
            </button>
          ))}
        </div>
        <ul className="space-y-1" data-testid="session-list">
          {shown.length === 0 && <li className="px-1 text-sm text-slate-400">No {scope} sessions.</li>}
          {shown.map((s) => (
            <li key={s.session_id}>
              <button
                onClick={() => onSelect(s.session_id)}
                className={`w-full rounded-lg border px-3 py-2 text-left text-sm ${selected === s.session_id ? "border-sky-400 bg-sky-50" : "border-slate-200 bg-white hover:bg-slate-50"}`}
                data-testid="session-row"
                data-state={s.state}
              >
                <div className="flex justify-between">
                  <span className="font-medium text-slate-800">#{shortId(s.session_id)}</span>
                  <span className="text-xs text-slate-500">{hhmm(s.started_at)}</span>
                </div>
                <div className="text-xs text-slate-600">
                  {STATE_LABEL[s.state] ?? s.state}
                  {s.basket_total ? ` · ${s.line_count} item(s) · ${rupees(s.basket_total)}` : ""}
                </div>
              </button>
            </li>
          ))}
        </ul>
      </div>
      <div className="min-h-0 overflow-y-auto rounded-lg border border-slate-200 bg-white">
        {selected ? (
          <TraceView sessionId={selected} version={versions[selected] ?? 0} products={products} />
        ) : (
          <p className="p-4 text-sm text-slate-400">Select a session to see its trace. Nothing here interrupts you; only a basket for review does.</p>
        )}
      </div>
    </div>
  );
}
