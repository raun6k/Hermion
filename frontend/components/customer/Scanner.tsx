"use client";

// Drag-to-scan (docs/frontend.md#drag-to-scan): the home screen's Scan QR reveals this dark scanner tile
// inside the phone. Drag it across to the shop's QR card in the merchant pane: scanner centre over the QR =>
// lock-on brackets; drop while locked => scan line, flash, beep => onScan(qr_token). Drop elsewhere => it
// springs back. Enter/Space on the focused tile scans without dragging (accessibility and tests).
import { useRef, useState, type KeyboardEvent, type PointerEvent } from "react";

interface Rect { left: number; top: number; width: number; height: number }

const findQr = (): { rect: Rect; token: string } | null => {
  const el = document.querySelector("[data-qr-target]");
  if (!el) return null;
  const r = el.getBoundingClientRect();
  return { rect: { left: r.left, top: r.top, width: r.width, height: r.height }, token: el.getAttribute("data-qr-token") ?? "" };
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

export function Scanner({ onScan, onCancel }: { onScan: (qrToken: string) => void | Promise<void>; onCancel: () => void }) {
  const tile = useRef<HTMLDivElement>(null);
  const start = useRef<{ x: number; y: number; cx: number; cy: number } | null>(null);
  const [offset, setOffset] = useState<{ dx: number; dy: number } | null>(null);
  const [target, setTarget] = useState<Rect | null>(null);
  const [phase, setPhase] = useState<"idle" | "locked" | "scanning" | "flash">("idle");

  const reset = () => {
    start.current = null;
    setOffset(null);
    setTarget(null);
    setPhase("idle");
  };

  async function runScan(token: string, rect: Rect) {
    setTarget(rect);
    setPhase("scanning");
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
    start.current = { x: e.clientX, y: e.clientY, cx: box.left + box.width / 2, cy: box.top + box.height / 2 };
    e.currentTarget.setPointerCapture(e.pointerId);
    setOffset({ dx: 0, dy: 0 });
  }

  function move(e: PointerEvent<HTMLDivElement>) {
    const s = start.current;
    if (!s) return;
    const dx = e.clientX - s.x;
    const dy = e.clientY - s.y;
    setOffset({ dx, dy });
    const qr = findQr();
    const x = s.cx + dx;
    const y = s.cy + dy;
    const over = qr && x >= qr.rect.left && x <= qr.rect.left + qr.rect.width && y >= qr.rect.top && y <= qr.rect.top + qr.rect.height;
    setTarget(over ? qr.rect : null);
    setPhase(over ? "locked" : "idle");
  }

  function up(e: PointerEvent<HTMLDivElement>) {
    if (!start.current) return;
    e.currentTarget.releasePointerCapture(e.pointerId);
    const qr = findQr();
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
      <div className="pointer-events-none absolute inset-x-0 bottom-8 flex flex-col items-center gap-2">
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
          className={`pointer-events-auto relative flex h-24 w-36 touch-none select-none flex-col items-center justify-center rounded-3xl border border-white/20 bg-slate-950 shadow-2xl ${dragging ? "cursor-grabbing" : "cursor-grab"}`}
          style={{
            transform: offset ? `translate(${offset.dx}px, ${offset.dy}px) scale(${dragging ? 1.08 : 1})` : undefined,
            transition: dragging ? "none" : "transform 380ms cubic-bezier(0.34, 1.56, 0.64, 1)",
            zIndex: 60,
          }}
        >
          {/* scanning corners */}
          {["left-2 top-2 border-l-2 border-t-2", "right-2 top-2 border-r-2 border-t-2", "bottom-2 left-2 border-b-2 border-l-2", "bottom-2 right-2 border-b-2 border-r-2"].map((c) => (
            <span key={c} className={`absolute h-3.5 w-3.5 rounded-[3px] border-pink-300 ${c}`} />
          ))}
          <svg viewBox="0 0 40 40" className="h-9 w-9" aria-hidden>
            <circle cx="20" cy="20" r="13" fill="#0b1220" stroke="#94a3b8" strokeWidth="2.5" />
            <circle cx="20" cy="20" r="6" fill="#1e3a8a" />
            <circle cx="16.5" cy="16.5" r="2.4" fill="#93c5fd" opacity="0.8" />
          </svg>
          <span className="mt-1 text-[10px] text-white/70">Drag onto the shop&apos;s QR</span>
        </div>
        <button onClick={onCancel} disabled={busy} className="pointer-events-auto rounded-full bg-white/15 px-4 py-1 text-xs text-white disabled:opacity-40" data-testid="scanner-cancel">
          Cancel
        </button>
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
