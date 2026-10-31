"use client";

import { translate } from "@/lib/i18n";

function names(code: string): { native: string; english: string } {
  const language = code.split("-")[0];
  try {
    return {
      native: new Intl.DisplayNames([code], { type: "language" }).of(language) ?? code,
      english: new Intl.DisplayNames(["en"], { type: "language" }).of(language) ?? code,
    };
  } catch {
    return { native: code, english: code };
  }
}

/** Round button for the control cluster that opens the language window. Sets the screen text language only. */
export function LanguageButton({ lang, onClick }: { lang: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={translate(lang, "chooseLanguage")}
      className="flex h-12 w-12 items-center justify-center rounded-full bg-white/15 text-white shadow-md transition active:scale-95"
      data-testid="language-button"
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className="h-5 w-5" aria-hidden>
        <path d="M4 5h12M10 3v2c0 5-2.7 8.1-6 9.5M6 8c1.4 2.7 3.7 5 6.5 6.4M14 20l3.5-9 3.5 9M15.2 17h4.6" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </button>
  );
}

/** Centered window over a blurred screen with one option per shop language. */
export function LanguageWindow({
  languages,
  selected,
  onChoose,
  onClose,
}: {
  languages: string[];
  selected: string;
  onChoose: (code: string) => void;
  onClose: () => void;
}) {
  return (
    <div
      className="absolute inset-0 z-40 flex items-center justify-center bg-slate-950/40 px-6 backdrop-blur-md"
      onClick={onClose}
      data-testid="language-window"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={translate(selected, "chooseLanguage")}
        className="flex h-[360px] w-[270px] flex-col rounded-3xl bg-white p-4 text-blue-950 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="mb-3 text-center text-base font-bold">{translate(selected, "chooseLanguage")}</h2>
        <div className="flex-1 space-y-2 overflow-y-auto pr-1" role="group">
          {languages.map((code) => {
            const n = names(code);
            const active = code === selected;
            return (
              <button
                key={code}
                type="button"
                onClick={() => onChoose(code)}
                aria-pressed={active}
                className={`flex h-12 w-full shrink-0 items-center justify-between rounded-2xl px-4 text-left transition ${active ? "bg-blue-900 text-white" : "bg-slate-100 hover:bg-pink-100"}`}
                data-testid={`ui-language-${code}`}
              >
                <span className="text-base font-semibold">{n.native}</span>
                {n.native !== n.english && <span className={`text-xs ${active ? "text-blue-100" : "text-slate-500"}`}>{n.english}</span>}
              </button>
            );
          })}
        </div>
        <button type="button" onClick={onClose} className="mx-auto mt-3 block text-sm font-medium text-blue-900 underline underline-offset-4" data-testid="language-close">
          {translate(selected, "close")}
        </button>
      </div>
    </div>
  );
}
