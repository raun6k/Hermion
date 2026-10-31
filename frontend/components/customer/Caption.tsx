"use client";

// Live caption stack (docs/upgrades-plan.md 4.4): the price card, then the last few spoken lines anchored at the
// bottom. Hermion's newest line streams in word by word; customer lines appear once STT finalizes them.
// ₹ amounts are highlighted as chips. Tap to open the full transcript.
import { Fragment, useEffect, useRef, useState } from "react";
import { rupees } from "@/lib/format";
import { translate } from "@/lib/i18n";

export interface CaptionLine {
  speaker: "customer" | "hermion";
  product_name: string | null;
  amount: string;
}
export interface SpokenLine {
  speaker: "customer" | "hermion";
  text: string;
  at: string; // HH:MM, for the full transcript
}

const AMOUNT = /(₹\s?\d[\d,]*(?:\.\d+)?)/g;

export function withChips(text: string) {
  return text.split(AMOUNT).map((part, i) =>
    AMOUNT.test(part) ? (
      <span key={i} className="mx-0.5 rounded-full bg-pink-200 px-1.5 py-0.5 font-bold text-pink-900" data-testid="price-chip">{part}</span>
    ) : (
      <Fragment key={i}>{part}</Fragment>
    ),
  );
}

function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const q = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReduced(q.matches);
    update();
    q.addEventListener("change", update);
    return () => q.removeEventListener("change", update);
  }, []);
  return reduced;
}

/** Reveals `text` word by word (about the pace of speech); instant when motion is reduced or text is old. */
function Streaming({ text, animate }: { text: string; animate: boolean }) {
  const words = text.split(" ");
  const [shown, setShown] = useState(animate ? 0 : words.length);
  useEffect(() => {
    if (!animate) return;
    const step = Math.min(90, 2500 / Math.max(words.length, 1));
    const t = setInterval(() => setShown((n) => (n >= words.length ? n : n + 1)), step);
    return () => clearInterval(t);
  }, [animate, words.length]);
  return <>{withChips(words.slice(0, animate ? shown : words.length).join(" "))}</>;
}

export function Caption({
  lang,
  caption,
  lines,
  onOpen,
}: {
  lang: string;
  caption: CaptionLine | null;
  lines: SpokenLine[];
  onOpen: () => void;
}) {
  const reduced = usePrefersReducedMotion();
  const windowRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const follow = useRef(true);
  useEffect(() => {
    const window = windowRef.current;
    const content = contentRef.current;
    if (!window || !content) return;
    const scrollToLatest = () => { if (follow.current) window.scrollTop = window.scrollHeight; };
    scrollToLatest();
    const observer = new ResizeObserver(scrollToLatest);
    observer.observe(content);
    return () => observer.disconnect();
  }, [lines]);
  return (
    <div className="mx-4 flex min-h-0 flex-1 flex-col gap-1.5 text-[#071844]">
      {caption && (
        <div key={`${caption.speaker}-${caption.amount}-${caption.product_name}`} className="hm-rise mx-auto rounded-2xl bg-white px-5 py-2 text-center shadow" data-testid="price-caption">
          <p className="text-xs font-semibold text-pink-700">{caption.speaker === "customer" ? translate(lang, "yourOffer") : caption.product_name ?? translate(lang, "hermionOffer")}</p>
          <p className="text-3xl font-bold tracking-tight">{rupees(caption.amount)}</p>
        </div>
      )}
      <div className="flex min-h-0 flex-1 flex-col rounded-2xl bg-white/10">
      <button type="button" onClick={onOpen} className="min-h-9 shrink-0 px-3 text-right text-xs font-semibold text-white/90 underline underline-offset-2" aria-label={translate(lang, "openConversation")}>{translate(lang, "conversation")}</button>
      <div ref={windowRef} role="region" aria-label={translate(lang, "conversation")} tabIndex={0} className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-2 pb-2 text-left" data-testid="caption-stack" onScroll={(e) => { const el = e.currentTarget; follow.current = el.scrollHeight - el.scrollTop - el.clientHeight < 32; }}>
        <span className="sr-only" aria-live="polite">{lines.length ? `${lines[lines.length - 1].speaker === "hermion" ? "Hermion" : "You"}: ${lines[lines.length - 1].text}` : ""}</span>
        <div ref={contentRef} className="space-y-1.5">
        {lines.map((l, i) => {
          const last = i === lines.length - 1;
          return (
            <span
              key={i}
              className={`hm-rise block max-w-[88%] break-words rounded-2xl px-3 py-1.5 text-sm leading-snug ${l.speaker === "customer" ? "ml-auto bg-white/90 text-right text-slate-700" : "bg-pink-50 text-[#182b59]"}`}
              data-testid={last ? "subtitle" : undefined}
            >
              {l.speaker === "customer" ? "You: " : ""}
              {l.speaker === "hermion" && last ? <Streaming text={l.text} animate={!reduced} /> : withChips(l.text)}
            </span>
          );
        })}
        {!caption && lines.length === 0 && <span className="block py-4 text-center text-sm text-white/70">{translate(lang, "convoEmpty")}</span>}
        </div>
      </div>
      </div>
    </div>
  );
}

/** Full scrollable transcript with timestamps. */
export function TranscriptSheet({ lang, lines, onClose }: { lang: string; lines: SpokenLine[]; onClose: () => void }) {
  return (
    <div className="absolute inset-x-2 bottom-[92px] top-16 z-20 flex flex-col rounded-3xl bg-white p-3 text-slate-900 shadow-2xl" role="dialog" aria-label={translate(lang, "conversation")} data-testid="transcript-sheet">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-sm font-semibold">{translate(lang, "conversation")}</h2>
        <button onClick={onClose} className="min-h-11 px-2 text-sm text-slate-500" >{translate(lang, "close")}</button>
      </div>
      <ol className="flex-1 space-y-2 overflow-y-auto text-sm">
        {lines.map((l, i) => (
          <li key={i} className={l.speaker === "customer" ? "text-right" : ""}>
            <span className="text-[11px] text-slate-400">{l.speaker === "customer" ? "You" : "Hermion"} · {l.at}</span>
            <p className={`mt-0.5 inline-block max-w-[90%] rounded-2xl px-3 py-1.5 ${l.speaker === "customer" ? "bg-slate-100" : "bg-pink-50"}`}>{withChips(l.text)}</p>
          </li>
        ))}
      </ol>
    </div>
  );
}
