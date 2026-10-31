"use client";

// A visual-only scanning view. QR matching uses the visible shop signs; Hermion never opens the browser camera.
import { translate } from "@/lib/i18n";

export function CameraView({ lang }: { lang: string }) {
  return (
    <div
      className="absolute inset-0 flex flex-col items-center justify-center overflow-hidden bg-[radial-gradient(circle_at_50%_38%,#1e3a8a,#020617_72%)] px-8 text-center"
      data-testid="camera-view"
      role="region"
      aria-label={translate(lang, "scanDrag")}
    >
      <div className="pointer-events-none absolute inset-0 shadow-[inset_0_0_80px_rgba(0,0,0,0.65)]" aria-hidden />
      <div className="relative h-40 w-full max-w-56" aria-hidden>
        {["left-0 top-0 border-l-2 border-t-2", "right-0 top-0 border-r-2 border-t-2", "bottom-0 left-0 border-b-2 border-l-2", "bottom-0 right-0 border-b-2 border-r-2"].map((c) => (
          <span key={c} className={`absolute h-8 w-8 rounded-sm border-white/90 ${c}`} />
        ))}
        <div className="hm-scanline absolute inset-x-0 top-0 h-0.5 bg-pink-400/80 shadow-[0_0_10px_#f472b6] motion-reduce:hidden" />
        <div className="absolute left-1/2 top-1/2 flex h-14 w-14 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-2xl border border-white/30 bg-white/10" aria-hidden>
          <svg viewBox="0 0 24 24" className="h-7 w-7 text-pink-200" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <path d="M4 9V4h5M15 4h5v5M20 15v5h-5M9 20H4v-5M8 8h2v2H8zM14 8h2v2h-2zM8 14h2v2H8zM14 14h2v2h-2z" />
          </svg>
        </div>
      </div>
      <p className="relative mt-5 max-w-56 text-sm font-medium text-white/80">{translate(lang, "scanDrag")}</p>
    </div>
  );
}
