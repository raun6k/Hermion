"use client";

function languageNames(code: string): { native: string; english: string } {
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

export function LanguageChoice({
  languages,
  pending,
  error,
  onChoose,
  onCancel,
  onRetry,
}: {
  languages: string[] | null;
  pending: boolean;
  error: string | null;
  onChoose: (code: string) => void;
  onCancel: () => void;
  onRetry: () => void;
}) {
  return (
    <div className="flex min-h-0 flex-1 flex-col px-6 pb-7 pt-10" data-testid="language-choice">
      <div className="text-center">
        <div className="mx-auto mb-5 flex h-14 w-14 items-center justify-center rounded-full bg-white/15 text-pink-200" aria-hidden>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" className="h-7 w-7">
            <path d="M4 5h12M10 3v2c0 5-2.7 8.1-6 9.5M6 8c1.4 2.7 3.7 5 6.5 6.4M14 20l3.5-9 3.5 9M15.2 17h4.6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>
        <h1 className="text-xl font-bold tracking-tight text-white">Choose your language</h1>
        <p className="mt-2 text-sm leading-5 text-blue-100">How would you like to speak with Hermion?</p>
      </div>
      {languages && languages.length > 0 ? (
        <div className="mt-7 grid min-h-0 grid-cols-2 gap-3 overflow-y-auto" role="group" aria-label="Choose one language">
          {languages.map((code) => {
            const names = languageNames(code);
            return (
              <button
                key={code}
                type="button"
                disabled={pending}
                onClick={() => onChoose(code)}
                className="min-h-20 rounded-2xl bg-white px-3 py-3 text-center text-blue-950 transition hover:bg-pink-100 disabled:cursor-wait disabled:opacity-60"
                data-testid={`choose-language-${code}`}
              >
                <span className="block text-base font-bold">{names.native}</span>
                {names.native !== names.english && <span className="mt-1 block text-xs text-blue-800">{names.english}</span>}
              </button>
            );
          })}
        </div>
      ) : !error ? (
        <p className="mt-8 text-center text-sm text-blue-100" role="status">Loading languages…</p>
      ) : null}
      {pending && <p className="mt-4 text-center text-sm text-blue-100" role="status">Getting Hermion ready…</p>}
      {error && (
        <div className="mt-4 rounded-xl bg-white px-3 py-2 text-sm text-red-800" role="alert">
          <p>{error}</p>
          {!languages && <button type="button" onClick={onRetry} className="mt-2 font-semibold underline">Try again</button>}
        </div>
      )}
      <button type="button" onClick={onCancel} className="mx-auto mt-auto pt-5 text-sm font-medium text-white underline underline-offset-4">Cancel</button>
    </div>
  );
}
