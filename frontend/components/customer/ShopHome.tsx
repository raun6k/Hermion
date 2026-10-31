"use client";

// The shop's home page on the customer's phone (docs/frontend.md#customer-pane-a-voice-call). Scanning the QR
// lands here, and so does sending the basket: "Talk to Hermion" is the main action; this device's baskets at
// the shop show with their status (waiting for approval, accepted, ...), then the shop page. Talking to Hermion
// with a basket that is waiting takes it back to change it (POST /sessions/{id}/rejoin).
import { rupees } from "@/lib/format";
import { translate, type TextKey } from "@/lib/i18n";
import type { SessionState, VisitPublic } from "@/lib/types";
import { Mascot } from "./Mascot";
import { ShopPage } from "./ShopPage";

const STATUS: Partial<Record<SessionState, { key: TextKey; tone: string }>> = {
  pending_merchant: { key: "visitPending", tone: "bg-amber-100 text-amber-900" },
  briefing: { key: "visitBriefing", tone: "bg-amber-100 text-amber-900" },
  in_person: { key: "inPerson", tone: "bg-violet-100 text-violet-900" },
  accepted: { key: "visitAccepted", tone: "bg-emerald-100 text-emerald-900" },
  declined: { key: "visitDeclined", tone: "bg-slate-200 text-slate-700" },
  exited: { key: "visitLeft", tone: "bg-slate-200 text-slate-700" },
  intro: { key: "visitOpen", tone: "bg-sky-100 text-sky-900" },
  discovery: { key: "visitOpen", tone: "bg-sky-100 text-sky-900" },
  negotiating: { key: "visitOpen", tone: "bg-sky-100 text-sky-900" },
};

export function ShopHome({
  lang,
  shopName,
  description,
  visits,
  current,
  busy,
  onTalk,
  onLeave,
  languageButton,
}: {
  lang: string;
  shopName: string;
  description: string;
  visits: VisitPublic[];
  current: SessionState | null; // state of this device's live session, if any
  busy: boolean;
  onTalk: () => void;
  onLeave: () => void;
  languageButton?: React.ReactNode;
}) {
  const t = (k: TextKey) => translate(lang, k);
  const paused = current === "in_person" ? t("pausedInPerson") : current === "briefing" ? t("preparing") : null;
  const hint = paused ?? (current === "pending_merchant" ? t("rejoinHint") : t("homeHint"));
  const baskets = visits.filter((v) => v.basket);
  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-y-auto pb-4" data-testid="shop-home" data-state={current ?? "none"}>
      <header className="px-6 pt-1 text-center">
        <h2 className="text-[19px] font-extrabold leading-tight">{shopName}</h2>
        <p className="text-xs text-white/75">{t("withHermion")} <span className="text-pink-400" aria-hidden>✦</span></p>
      </header>

      <section className="flex flex-col items-center gap-3 px-6 pt-2">
        <Mascot state={current === "pending_merchant" || current === "briefing" ? "thinking" : current === "accepted" ? "happy" : "idle"} compact />
        <button
          onClick={onTalk}
          disabled={busy || paused !== null}
          className="flex min-h-14 w-full items-center justify-center gap-3 rounded-full bg-white px-6 text-base font-extrabold text-[#071844] shadow-[0_10px_30px_rgba(236,72,153,0.35)] ring-4 ring-pink-400/40 transition active:scale-[0.98] disabled:opacity-60"
          data-testid="talk-to-hermion"
        >
          <span className="flex h-9 w-9 items-center justify-center rounded-full bg-pink-600 text-white" aria-hidden>
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"><rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3" /></svg>
          </span>
          {t("talkToHermion")}
        </button>
        <p className="text-center text-xs leading-snug text-white/80" data-testid="home-hint">{hint}</p>
      </section>

      {baskets.length > 0 && (
        <section className="mx-3 mt-4" aria-labelledby="your-baskets">
          <h3 id="your-baskets" className="mb-2 px-1 text-[11px] font-bold uppercase tracking-[0.12em] text-white/70">{t("yourBaskets")}</h3>
          <ul className="space-y-2">
            {baskets.map((v) => {
              const status = STATUS[v.state];
              return (
                <li key={v.session_id} className="rounded-3xl bg-white p-3.5 text-[#071844] shadow" data-testid="visit" data-state={v.state}>
                  <div className="flex items-center justify-between gap-2">
                    {status && <span className={`rounded-full px-2.5 py-1 text-[11px] font-bold ${status.tone}`} data-testid="visit-status">{t(status.key)}</span>}
                    <span className="text-lg font-extrabold tabular-nums">{rupees(v.basket!.total)}</span>
                  </div>
                  <ul className="mt-2 space-y-0.5 text-xs text-[#415981]">
                    {v.basket!.lines.map((l) => (
                      <li key={l.product_id} className="flex justify-between gap-2">
                        <span className="truncate">{l.qty > 1 ? `${l.qty}× ` : ""}{l.product_name}</span>
                        <span className="tabular-nums">{rupees(l.line_total)}</span>
                      </li>
                    ))}
                  </ul>
                </li>
              );
            })}
          </ul>
        </section>
      )}

      <div className="mt-4">
        <ShopPage lang={lang} name={shopName} description={description} />
      </div>

      <div className="mt-4 flex items-center justify-center gap-4">
        {languageButton}
        <button onClick={onLeave} className="min-h-11 rounded-full px-4 text-sm font-medium text-white/80 ring-1 ring-white/25" data-testid="leave-shop">{t("leaveShop")}</button>
      </div>
    </div>
  );
}
