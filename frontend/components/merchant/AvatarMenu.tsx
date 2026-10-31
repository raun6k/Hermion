"use client";

import { useEffect, useRef, useState } from "react";
import type { MerchantChoice } from "@/lib/types";

// The account button: a person icon that shows who is signed in and switches between the demo shops.
// Demo-only switching; a real deployment would sign in instead.
export function AvatarMenu({
  shops,
  current,
  onSwitch,
}: {
  shops: MerchantChoice[];
  current: string | null;
  onSwitch: (id: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !box.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);
  const name = shops.find((s) => s.merchant_id === current)?.shop_name ?? "Shop";
  return (
    <div className="relative" ref={box}>
      <button
        onClick={() => setOpen((o) => !o)}
        aria-label={`Account: ${name}. Switch shop`}
        aria-expanded={open}
        aria-haspopup="menu"
        className="flex min-h-10 items-center gap-1.5 rounded-full bg-[#071f5c] py-1 pl-1 pr-3 text-white shadow-sm transition hover:bg-[#0b2a78]"
        data-testid="avatar"
      >
        <span className="flex h-8 w-8 items-center justify-center rounded-full bg-white/15" aria-hidden>
          <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
            <circle cx="12" cy="8.5" r="3.5" />
            <path d="M5 20c1.2-3.6 4-5.5 7-5.5s5.8 1.9 7 5.5" />
          </svg>
        </span>
        <svg viewBox="0 0 12 12" className={`h-3 w-3 transition ${open ? "rotate-180" : ""}`} fill="currentColor" aria-hidden><path d="M2 4l4 4 4-4z" /></svg>
      </button>
      {open && (
        <ul role="menu" className="absolute right-0 top-full z-20 mt-2 w-64 rounded-2xl bg-white p-2 text-[#081b4d] shadow-xl ring-1 ring-sky-100" data-testid="avatar-menu">
          <li className="border-b border-sky-50 px-3 pb-2 pt-1" role="none">
            <span className="block text-xs text-[#415981]">Signed in as</span>
            <span className="block text-sm font-bold">{name}</span>
          </li>
          <li className="px-3 pb-1 pt-3 text-sm font-bold text-[#071844]" role="none">Switch shop</li>
          <li className="px-3 pb-2 text-xs leading-5 text-[#5b6f94]" role="none">
            Choose a shop to view its customers, approvals, products, settings, and insights.
          </li>
          {shops.map((s) => (
            <li key={s.merchant_id} role="none">
              <button
                role="menuitemradio"
                aria-checked={s.merchant_id === current}
                onClick={() => {
                  setOpen(false);
                  onSwitch(s.merchant_id);
                }}
                className={`flex min-h-11 w-full items-center justify-between gap-3 rounded-xl border border-transparent px-3 py-2 text-left text-sm transition hover:bg-sky-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-pink-200 ${s.merchant_id === current ? "bg-sky-50 font-semibold text-[#071844]" : "text-[#253d70]"}`}
                data-testid={`shop-${s.merchant_id}`}
              >
                {s.shop_name}
                {s.merchant_id === current && (
                  <svg viewBox="0 0 20 20" className="h-4 w-4 shrink-0 text-pink-600" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <path d="m4 10 4 4 8-8" />
                  </svg>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
