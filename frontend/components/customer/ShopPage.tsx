"use client";

// A short shop introduction and customer promises support the voice conversation without turning the home screen into a catalog.
import { translate, type TextKey } from "@/lib/i18n";

const PROMISES: { key: TextKey; icon: string }[] = [
  { key: "badgeLanguage", icon: "M4 5h12M10 3v2c0 5-2.7 8.1-6 9.5M6 8c1.4 2.7 3.7 5 6.5 6.4M14 20l3.5-9 3.5 9M15.2 17h4.6" },
  { key: "badgeFinal", icon: "M12 3l7 3v5c0 4.5-3 8.3-7 10-4-1.7-7-5.5-7-10V6l7-3Zm-3 9 2 2 4-4" },
  { key: "badgePay", icon: "M3 7h18v10H3zM3 11h18M7 15h3" },
];

export function ShopPage({ lang, name, description }: { lang: string; name: string; description: string }) {
  return (
    <section className="hm-rise mx-3 flex flex-col gap-2.5" data-testid="shop-page" aria-label={name}>
      <div className="rounded-[26px] bg-white p-3.5 text-[#071844] shadow-[0_12px_30px_rgba(2,8,40,0.35)]">
        <header className="flex items-center gap-3">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-pink-500 to-fuchsia-600 text-lg font-extrabold text-white" aria-hidden>
            {name.slice(0, 1)}
          </span>
          {description && <p className="line-clamp-3 text-xs leading-snug text-[#4a5f86]">{description}</p>}
        </header>
      </div>
      <ul className="grid grid-cols-3 gap-1.5">
        {PROMISES.map(({ key, icon }) => (
          <li key={key} className="flex flex-col items-center gap-1 rounded-2xl bg-white/10 px-1.5 py-2 text-center text-[10px] leading-tight text-white/90">
            <svg viewBox="0 0 24 24" className="h-4 w-4 text-pink-300" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
              <path d={icon} />
            </svg>
            {translate(lang, key)}
          </li>
        ))}
      </ul>
    </section>
  );
}
