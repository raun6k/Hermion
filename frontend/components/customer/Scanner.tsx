"use client";

// Drag-to-scan (docs/frontend.md#drag-to-scan): the home screen's Scan QR reveals this dark scanner tile
// inside the phone. Drag the phone's back onto a shop's QR sign: its camera module (or its middle) over the QR =>
// lock-on brackets; drop while locked => scan line, flash, beep => onScan(qr_token). Drop elsewhere => it
// springs back. Enter/Space on the focused tile scans without dragging (accessibility and tests).
import { translate } from "@/lib/i18n";
import { useRef, useState, type KeyboardEvent, type PointerEvent } from "react";

interface Rect { left: number; top: number; width: number; height: number }

// The QR under the point (drag), or the first one (keyboard).
const findQr = (x?: number, y?: number): { rect: Rect; token: string } | null => {
  for (const el of document.querySelectorAll("[data-qr-target]")) {
    const r = el.getBoundingClientRect();
    if (x === undefined || y === undefined || (x >= r.left && x <= r.right && y >= r.top && y <= r.bottom))
      return { rect: { left: r.left, top: r.top, width: r.width, height: r.height }, token: el.getAttribute("data-qr-token") ?? "" };
  }
  return null;
};

function beep() {
  try {
    const ctx = new AudioContext();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.frequency.value = 1040;
    gain.gain.value = 0.08;
    osc.connect(gain).connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 0.12);
    osc.onended = () => void ctx.close();
  } catch {
    // audio is a nicety
  }
}

export function Scanner({ onScan, onCancel, onPhase, lang = "en-IN" }: { onScan: (qrToken: string) => void | Promise<void>; onCancel?: () => void; onPhase?: (phase: string) => void; lang?: string }) {
  const tile = useRef<HTMLDivElement>(null);
  const lock = useRef<{ rect: Rect; token: string } | null>(null);
  const start = useRef<{ x: number; y: number; cx: number; cy: number; mx: number; my: number } | null>(null);
  const [offset, setOffset] = useState<{ dx: number; dy: number } | null>(null);
  const [target, setTarget] = useState<Rect | null>(null);
  const [phase, setPhase] = useState<"idle" | "locked" | "scanning" | "flash">("idle");

  const reset = () => {
    start.current = null;
    setOffset(null);
    setTarget(null);
    setPhase("idle");
    onPhase?.("idle");
  };

  async function runScan(token: string, rect: Rect) {
    setTarget(rect);
    setPhase("scanning");
    onPhase?.("scanning");
    await new Promise((r) => setTimeout(r, 750));
    setPhase("flash");
    beep();
    await onScan(token);
    await new Promise((r) => setTimeout(r, 400));
    reset();
  }

  function down(e: PointerEvent<HTMLDivElement>) {
    if (phase === "scanning" || phase === "flash") return;
    const box = tile.current!.getBoundingClientRect();
    // Aim with the camera module (top-left of the phone's back); the middle of the phone also counts.
    start.current = { x: e.clientX, y: e.clientY, cx: box.left + box.width * 0.3, cy: box.top + box.height * 0.19, mx: box.left + box.width / 2, my: box.top + box.height / 2 };
    e.currentTarget.setPointerCapture(e.pointerId);
    setOffset({ dx: 0, dy: 0 });
  }

  function move(e: PointerEvent<HTMLDivElement>) {
    const s = start.current;
    if (!s) return;
    const dx = e.clientX - s.x;
    const dy = e.clientY - s.y;
    setOffset({ dx, dy });
    const qr = findQr(s.cx + dx, s.cy + dy) ?? findQr(s.mx + dx, s.my + dy);
    setTarget(qr ? qr.rect : null);
    lock.current = qr;
    setPhase(qr ? "locked" : "idle");
  }

  function up(e: PointerEvent<HTMLDivElement>) {
    if (!start.current) return;
    e.currentTarget.releasePointerCapture(e.pointerId);
    const qr = lock.current;
    if (phase === "locked" && qr) {
      start.current = null;
      void runScan(qr.token, qr.rect);
    } else reset();
  }

  function key(e: KeyboardEvent<HTMLDivElement>) {
    if (phase !== "idle" || (e.key !== "Enter" && e.key !== " ")) return;
    e.preventDefault();
    const qr = findQr();
    if (qr) void runScan(qr.token, qr.rect);
  }

  const busy = phase === "scanning" || phase === "flash";
  const dragging = offset !== null && !busy;
  return (
    <>
      <div className="flex flex-col items-center gap-1">
        <div
          ref={tile}
          role="button"
          tabIndex={0}
          aria-label="Scanner: drag onto the shop's QR code"
          onPointerDown={down}
          onPointerMove={move}
          onPointerUp={up}
          onPointerCancel={reset}
          onKeyDown={key}
          data-testid="scanner"
          data-phase={phase}
          className={`pointer-events-auto relative flex h-[84px] w-12 touch-none select-none ${dragging ? "cursor-grabbing" : "cursor-grab"}`}
          style={{
            transform: offset ? `translate(${offset.dx}px, ${offset.dy}px) scale(${dragging ? 1.08 : 1})` : undefined,
            transition: dragging ? "none" : "transform 380ms cubic-bezier(0.34, 1.56, 0.64, 1)",
            zIndex: 60,
          }}
        >
          {/* The back of a phone: its rear camera module is what you point at the QR. */}
          <svg viewBox="0 0 56 96" className="h-full w-full drop-shadow-[0_8px_12px_rgba(0,0,0,0.6)]" aria-hidden>
            <defs>
              <linearGradient id="back-body" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0" stopColor="#3b4a6b" />
                <stop offset="0.55" stopColor="#1e2a47" />
                <stop offset="1" stopColor="#111a30" />
              </linearGradient>
              <linearGradient id="back-bump" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0" stopColor="#4b5d85" />
                <stop offset="1" stopColor="#24314f" />
              </linearGradient>
              <radialGradient id="back-lens" cx="0.35" cy="0.3" r="0.8">
                <stop offset="0" stopColor="#7aa2ff" />
                <stop offset="0.4" stopColor="#1d2b6b" />
                <stop offset="1" stopColor="#03060f" />
              </radialGradient>
            </defs>
            <rect x="2" y="2" width="52" height="92" rx="11" fill="url(#back-body)" stroke="#6b7da6" strokeWidth="1.2" />
            <rect x="5" y="5" width="25" height="27" rx="8" fill="url(#back-bump)" stroke="#7f92bd" strokeWidth="0.8" />
            {[
              [12, 12],
              [12, 24],
              [23, 18],
            ].map(([cx, cy]) => (
              <g key={`${cx}-${cy}`}>
                <circle cx={cx} cy={cy} r="5" fill="#0b1122" stroke="#9aa9cc" strokeWidth="0.9" />
                <circle cx={cx} cy={cy} r="3.4" fill="url(#back-lens)" />
                <circle cx={cx - 1.2} cy={cy - 1.2} r="0.9" fill="#fff" opacity="0.75" />
              </g>
            ))}
            <circle cx="24" cy="9" r="1.6" fill="#fef3c7" />
            <path d="M28 66l2 4 4 2-4 2-2 4-2-4-4-2 4-2Z" fill="#f472b6" opacity="0.85" />
          </svg>
        </div>
        {onCancel && (
          <button onClick={onCancel} disabled={busy} className="pointer-events-auto rounded-full bg-white/15 px-4 py-1 text-xs text-white disabled:opacity-40" data-testid="scanner-cancel">
            {translate(lang, "cancel")}
          </button>
        )}
      </div>

      {target && phase !== "idle" && (
        <div className="pointer-events-none fixed z-[70]" style={{ left: target.left - 8, top: target.top - 8, width: target.width + 16, height: target.height + 16 }} data-testid="lock-on" data-phase={phase}>
          {["left-0 top-0 border-l-4 border-t-4", "right-0 top-0 border-r-4 border-t-4", "bottom-0 left-0 border-b-4 border-l-4", "bottom-0 right-0 border-b-4 border-r-4"].map((c) => (
            <span key={c} className={`absolute h-6 w-6 rounded-sm border-pink-500 ${c}`} />
          ))}
          {phase === "scanning" && <div className="hm-scanline absolute inset-x-0 top-0 h-1 bg-pink-500/80 shadow-[0_0_12px_#ec4899]" />}
          {phase === "flash" && <div className="hm-flash absolute inset-0 bg-white" />}
        </div>
      )}
    </>
  );
}
