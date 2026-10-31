import { rupees } from "@/lib/format";

export interface CaptionLine {
  speaker: "customer" | "hermion";
  product_name: string | null;
  amount: string;
}

// Price caption under the mascot for every amount heard or said, plus the latest spoken line.
export function Caption({ caption, line }: { caption: CaptionLine | null; line: { speaker: "customer" | "hermion"; text: string } | null }) {
  return (
    <div className="mx-5 min-h-[104px] rounded-2xl bg-white px-4 py-3 text-center text-[#071844]" aria-live="polite">
      {caption && (
        <div key={`${caption.speaker}-${caption.amount}-${caption.product_name}`} data-testid="price-caption">
          <p className="text-xs font-semibold text-pink-700">{caption.speaker === "customer" ? "Your offer" : caption.product_name ?? "Hermion’s offer"}</p>
          <p className="mt-1 text-3xl font-bold tracking-tight">{rupees(caption.amount)}</p>
        </div>
      )}
      {line && (
        <p className="mt-2 rounded-xl bg-pink-50 px-3 py-2 text-sm leading-snug text-[#182b59]" data-testid="subtitle">
          {line.speaker === "customer" ? `You: ${line.text}` : line.text}
        </p>
      )}
      {!caption && !line && <p className="py-4 text-sm text-[#415981]">Your conversation will appear here.</p>}
    </div>
  );
}
