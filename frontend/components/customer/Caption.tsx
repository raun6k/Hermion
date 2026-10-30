import { rupees } from "@/lib/format";

export interface CaptionLine {
  speaker: "customer" | "hermion";
  product_name: string | null;
  amount: string;
}

// Price caption under the mascot for every amount heard or said, plus the latest spoken line.
export function Caption({ caption, line }: { caption: CaptionLine | null; line: { speaker: "customer" | "hermion"; text: string } | null }) {
  return (
    <div className="min-h-[104px] px-5 text-center" aria-live="polite">
      {caption && (
        <p
          key={`${caption.speaker}-${caption.amount}-${caption.product_name}`}
          className={`mx-auto mb-2 inline-block rounded-full px-4 py-1 text-sm font-semibold shadow-sm ${caption.speaker === "customer" ? "bg-white text-blue-950" : "bg-pink-300 text-blue-950"}`}
          data-testid="price-caption"
        >
          {caption.speaker === "customer" ? `You: ${rupees(caption.amount)}` : `${caption.product_name ? `${caption.product_name} · ` : ""}${rupees(caption.amount)}`}
        </p>
      )}
      {line && (
        <p className={`text-[13px] leading-snug ${line.speaker === "hermion" ? "text-white" : "text-white/60"}`} data-testid="subtitle">
          {line.speaker === "customer" ? `You: ${line.text}` : line.text}
        </p>
      )}
    </div>
  );
}
