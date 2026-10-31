"use client";

import { useState } from "react";
import { translate } from "@/lib/i18n";

// The More sheet (docs/frontend.md): View basket and a text box to type to Hermion (the keypad path the
// integration tests use). The full conversation opens by tapping the captions, not from here.
export function MoreSheet({
  lang,
  basketCount,
  canType,
  onViewBasket,
  onSwitchShop,
  onSend,
  onClose,
}: {
  lang: string;
  basketCount: number;
  canType: boolean;
  onViewBasket: () => void;
  onSwitchShop: () => void;
  onSend: (text: string) => void;
  onClose: () => void;
}) {
  const [draft, setDraft] = useState("");
  const submit = () => {
    const text = draft.trim();
    if (!text || !canType) return;
    onSend(text);
    setDraft("");
  };

  return (
    <div className="absolute inset-x-2 bottom-[92px] z-20 max-h-[62%] space-y-2 overflow-y-auto rounded-3xl bg-white p-3 text-slate-900 shadow-[0_-8px_30px_rgba(0,0,0,0.35)]" data-testid="more-sheet" role="dialog" aria-label={translate(lang, "more")}>
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold">{translate(lang, "more")}</h2>
        <button onClick={onClose} className="min-h-11 px-2 text-sm text-slate-500">{translate(lang, "close")}</button>
      </div>

      <button onClick={onViewBasket} className="flex w-full items-center justify-between rounded-xl bg-blue-50 px-3 py-2 text-sm font-medium text-blue-900" data-testid="view-basket">
        <span>{translate(lang, "viewBasket")}</span>
        <span className="rounded-full bg-blue-900 px-2 text-xs font-bold text-white" aria-hidden>{basketCount}</span>
      </button>
      <button type="button" onClick={onSwitchShop} className="flex min-h-11 w-full items-center rounded-xl bg-blue-50 px-3 py-2 text-left text-sm font-medium text-blue-900" data-testid="switch-shop">
        {translate(lang, "leaveShop")}
      </button>

      <form
        className="flex gap-2 rounded-xl bg-slate-50 p-2"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={translate(lang, "typeMessage")}
          disabled={!canType}
          className="min-w-0 flex-1 bg-transparent px-2 py-1.5 text-sm outline-none disabled:opacity-50"
          data-testid="keypad-input"
          aria-label={translate(lang, "typeMessage")}
        />
        <button disabled={!canType || !draft.trim()} className="rounded-lg bg-blue-900 px-3 text-sm text-white disabled:opacity-40" data-testid="keypad-send">
          {translate(lang, "send")}
        </button>
      </form>
    </div>
  );
}
