import type { AgentState } from "@/lib/types";

// CSS/SVG robot fallback (Q14). Reacts only to `agent_state`; image assets (public/mascot/<state>.webp)
// can replace the face later without touching callers.
const GLOW: Record<AgentState, string> = {
  idle: "#f9a8d4",
  listening: "#60a5fa",
  thinking: "#f9a8d4",
  speaking: "#f9a8d4",
  happy: "#fcd34d",
  negotiating: "#c4b5fd",
};

function Eyes({ state }: { state: AgentState }) {
  const arc = state === "speaking" || state === "happy";
  if (arc)
    return (
      <g stroke="#e0e7ff" strokeWidth="6" strokeLinecap="round" fill="none">
        <path d="M70 100 q10 -12 20 0" />
        <path d="M110 100 q10 -12 20 0" />
      </g>
    );
  const dy = state === "listening" ? -6 : state === "thinking" ? 2 : 0;
  const h = state === "thinking" ? 8 : 16;
  return (
    <g fill="#e0e7ff">
      <rect x="70" y={92 + dy} width="18" height={h} rx="3" />
      <rect x="112" y={92 + dy} width="18" height={h} rx="3" />
    </g>
  );
}

export function Mascot({ state }: { state: AgentState }) {
  const glow = GLOW[state];
  const bars = state === "listening" || state === "speaking";
  return (
    <div className="relative mx-auto h-52 w-52" data-testid="mascot" data-state={state} role="img" aria-label={`Hermion is ${state}`}>
      <svg viewBox="0 0 200 200" className="h-full w-full overflow-visible">
        {/* glowing rings */}
        <circle cx="100" cy="100" r="86" fill={glow} opacity="0.18" />
        <circle cx="100" cy="100" r="70" fill="none" stroke={glow} strokeWidth="2" opacity="0.6" />
        {(state === "speaking" || state === "listening") && (
          <>
            <circle cx="100" cy="100" r="70" fill="none" stroke={glow} strokeWidth="3" className="hm-ring" style={{ transformOrigin: "100px 100px" }} />
            <circle cx="100" cy="100" r="70" fill="none" stroke={glow} strokeWidth="2" className="hm-ring" style={{ transformOrigin: "100px 100px", animationDelay: "0.8s" }} />
          </>
        )}
        {state === "negotiating" && (
          <g className="hm-orbit" fill="none" stroke={glow} strokeWidth="3">
            <ellipse cx="100" cy="100" rx="92" ry="34" opacity="0.7" />
            <ellipse cx="100" cy="100" rx="34" ry="92" opacity="0.5" />
            <circle cx="192" cy="100" r="6" fill={glow} />
          </g>
        )}
        <g className="hm-float">
          {/* antenna + head */}
          <line x1="100" y1="42" x2="100" y2="58" stroke="#475569" strokeWidth="4" />
          <circle cx="100" cy="38" r="6" fill={glow} />
          <rect x="44" y="58" width="112" height="92" rx="30" fill="#101d3f" stroke="#7187b7" strokeWidth="3" />
          <rect x="54" y="70" width="92" height="62" rx="20" fill="#050b1d" />
          <Eyes state={state} />
          {state === "negotiating" && (
            <g clipPath="url(#face)">
              <rect x="54" y="70" width="92" height="3" fill={glow} opacity="0.9" className="hm-scanline" style={{ transformBox: "fill-box" }} />
            </g>
          )}
          <clipPath id="face">
            <rect x="54" y="70" width="92" height="62" rx="20" />
          </clipPath>
          {/* thinking: hand on chin */}
          {state === "thinking" && <path d="M92 150 q8 -14 20 -6 q4 8 -4 14 q-10 4 -16 -8z" fill="#fde68a" stroke="#d6b656" strokeWidth="2" />}
        </g>
        {bars && (
          <g fill={glow}>
            {[0, 1, 2, 3, 4].map((i) => (
              <rect key={i} x={72 + i * 12} y="164" width="6" height="22" rx="3" className="hm-bar" style={{ animationDelay: `${i * 0.12}s` }} />
            ))}
          </g>
        )}
        {state === "thinking" && (
          <g fill={glow}>
            {[0, 1, 2].map((i) => (
              <circle key={i} cx={150 + i * 10} cy={50 - i * 8} r={3 + i} className="hm-dot" style={{ animationDelay: `${i * 0.25}s` }} />
            ))}
          </g>
        )}
        {state === "happy" && (
          <g fill="#fbbf24">
            {[[38, 52], [164, 44], [172, 112], [30, 120]].map(([x, y], i) => (
              <path key={i} d={`M${x} ${y - 9} l3 6 6 3 -6 3 -3 6 -3 -6 -6 -3 6 -3z`} className="hm-sparkle" style={{ animationDelay: `${i * 0.3}s` }} />
            ))}
          </g>
        )}
      </svg>
    </div>
  );
}
