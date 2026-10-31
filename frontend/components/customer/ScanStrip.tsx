"use client";

// This scan strip appears only after the customer taps Scan QR. It holds a visual phone back, an arrow and shop QR signs.
import type { MerchantChoice } from "@/lib/types";
import { translate } from "@/lib/i18n";
import { Scanner } from "./Scanner";
import { ShopQR } from "./ShopQR";

export function ScanStrip({
  shops,
  onScan,
  onCancel,
  lang,
}: {
  shops: MerchantChoice[];
  onScan: (token: string) => void | Promise<void>;
  onCancel: () => void;
  lang: string;
}) {
  return (
    <div className="flex w-full max-w-[460px] shrink-0 flex-col gap-1 rounded-2xl bg-white/5 px-3 py-2 text-white" data-testid="scan-strip">
      <p className="text-center text-xs text-white/70">{translate(lang, "scannerHint")}</p>
      <div className="flex items-center justify-center gap-3">
        <Scanner onScan={onScan} onCancel={onCancel} lang={lang} />
        <svg viewBox="0 0 48 24" className="h-5 w-8 shrink-0 text-pink-300" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
          <path d="M2 12h40M32 4l10 8-10 8" />
        </svg>
        <div className="flex min-w-0 gap-1.5">
          {shops.map((s) => (
            <ShopQR key={s.merchant_id} token={s.qr_token} label={s.shop_name} onTap={() => void onScan(s.qr_token)} />
          ))}
        </div>
      </div>
    </div>
  );
}
