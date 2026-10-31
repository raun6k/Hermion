import type { ReactNode } from "react";

// Phone chrome: status bar, Dynamic Island, deep-blue screen (docs/frontend.md). `overlay` renders above the
// screen but outside its rounded clip, so the draggable scanner can leave the phone.
export function PhoneFrame({ children, status, overlay }: { children: ReactNode; status?: ReactNode; overlay?: ReactNode }) {
  return (
    <div className="relative h-[660px] w-[330px]" data-testid="phone">
      <div className="absolute inset-0 flex flex-col overflow-hidden rounded-[44px] border-[9px] border-slate-950 bg-[#062a86] text-white shadow-[0_10px_32px_rgba(0,0,0,0.5)]">
        <div className="flex items-center justify-between px-7 pt-2 text-[11px] font-semibold text-white/90">
          <span>9:41</span>
          <span className="absolute left-1/2 top-2 h-6 w-24 -translate-x-1/2 rounded-full bg-slate-950" aria-hidden />
          <span aria-hidden>●●● ▮</span>
        </div>
        {status && <div className="mt-5 text-center text-xs font-medium text-white/80">{status}</div>}
        <div className="relative flex min-h-0 flex-1 flex-col">{children}</div>
      </div>
      {overlay && <div className="pointer-events-none absolute inset-0 z-30">{overlay}</div>}
    </div>
  );
}
