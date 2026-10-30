"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { SessionPublic } from "@/lib/types";

export interface ConversationLine {
  speaker: "customer" | "hermion";
  text: string;
}

// The expandable More sheet (docs/frontend.md): View basket, Conversation, Language. A plain text box stays
// at the top as the text-input test tool (the typed path the integration tests and the keypad fallback use).
export function MoreSheet({
  sessionId,
  conversation,
  basketCount,
  canType,
  onViewBasket,
  onSend,
  onLanguage,
  onClose,
}: {
  sessionId: string;
  conversation: ConversationLine[];
  basketCount: number;
  canType: boolean;
  onViewBasket: () => void;
  onSend: (text: string) => void;
  onLanguage: (code: string | null) => void;
  onClose: () => void;
}) {
  const [draft, setDraft] = useState("");
  const [info, setInfo] = useState<SessionPublic | null>(null);
  const [pinned, setPinned] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    api.session(sessionId).then((s) => live && setInfo(s)).catch(() => {});
    return () => {
      live = false;
    };
  }, [sessionId]);

  const name = (code: string) => {
    try {
      return new Intl.DisplayNames(["en"], { type: "language" }).of(code) ?? code;
    } catch {
      return code;
    }
  };
  const submit = () => {
    const text = draft.trim();
    if (!text || !canType) return;
    onSend(text);
    setDraft("");
  };
  const choose = (code: string | null) => {
    setPinned(code);
    onLanguage(code);
  };

  return (
    <div className="absolute inset-x-2 bottom-[92px] z-20 max-h-[62%] space-y-2 overflow-y-auto rounded-3xl bg-white p-3 text-slate-900 shadow-[0_-8px_30px_rgba(0,0,0,0.35)]" data-testid="more-sheet" role="dialog" aria-label="More">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold">More</h2>
        <button onClick={onClose} className="text-xs text-slate-500" aria-label="Close more">Close</button>
      </div>

      <button onClick={onViewBasket} className="flex w-full items-center justify-between rounded-xl bg-blue-50 px-3 py-2 text-sm font-medium text-blue-900" data-testid="view-basket">
        <span>View basket</span>
        <span className="text-xs text-blue-700">{basketCount ? `${basketCount} item(s)` : "empty"}</span>
      </button>

      <details className="rounded-xl bg-slate-50 px-3 py-2 text-sm">
        <summary className="cursor-pointer font-medium">Conversation</summary>
        <ol className="mt-2 max-h-36 space-y-1 overflow-y-auto text-xs" data-testid="conversation">
          {conversation.length === 0 && <li className="text-slate-400">Nothing yet.</li>}
          {conversation.map((l, i) => (
            <li key={i} className={l.speaker === "customer" ? "text-slate-500" : "text-slate-900"}>
              <span className="font-medium">{l.speaker === "customer" ? "You" : "Hermion"}:</span> {l.text}
            </li>
          ))}
        </ol>
      </details>

      <details className="rounded-xl bg-slate-50 px-3 py-2 text-sm" data-testid="language-section">
        <summary className="cursor-pointer font-medium">Language</summary>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {[null, ...(info?.languages ?? [])].map((code) => (
            <button
              key={code ?? "auto"}
              onClick={() => choose(code)}
              aria-pressed={pinned === code}
              className={`rounded-full px-3 py-1 text-xs ${pinned === code ? "bg-blue-900 text-white" : "bg-white text-slate-700 ring-1 ring-slate-300"}`}
              data-testid={`language-${code ?? "auto"}`}
            >
              {code === null ? "Auto" : name(code)}
            </button>
          ))}
        </div>
      </details>

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
          placeholder="Text input (test tool)"
          disabled={!canType}
          className="min-w-0 flex-1 bg-transparent px-2 py-1.5 text-sm outline-none disabled:opacity-50"
          data-testid="keypad-input"
          aria-label="Type a message to Hermion"
        />
        <button disabled={!canType || !draft.trim()} className="rounded-lg bg-blue-900 px-3 text-sm text-white disabled:opacity-40" data-testid="keypad-send">
          Send
        </button>
      </form>
    </div>
  );
}
