const btn = "flex h-14 w-14 items-center justify-center rounded-full shadow-md transition active:scale-95";

export function CallControls({
  muted,
  moreOpen,
  onMute,
  onEnd,
  onMore,
}: {
  muted: boolean;
  moreOpen: boolean;
  onMute: () => void;
  onEnd: () => void;
  onMore: () => void;
}) {
  return (
    <div className="relative z-10 flex items-center justify-center gap-7 pb-5 pt-2">
      <button onClick={onMute} aria-pressed={muted} aria-label={muted ? "Unmute" : "Mute"} className={`${btn} ${muted ? "bg-pink-300 text-blue-950" : "bg-white/15 text-white"}`} data-testid="mute">
        <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
          <rect x="9" y="3" width="6" height="11" rx="3" />
          <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
          {muted && <path d="M4 4l16 16" />}
        </svg>
      </button>
      <button onClick={onEnd} aria-label="End call" className={`${btn} h-16 w-16 bg-red-600 text-white`} data-testid="end-call">
        <svg viewBox="0 0 24 24" className="h-7 w-7 rotate-[135deg]" fill="currentColor"><path d="M6.6 10.8a15 15 0 0 0 6.6 6.6l2.2-2.2a1 1 0 0 1 1-.25 11 11 0 0 0 3.5.55 1 1 0 0 1 1 1V20a1 1 0 0 1-1 1A17 17 0 0 1 3 4a1 1 0 0 1 1-1h3.5a1 1 0 0 1 1 1c0 1.2.2 2.4.55 3.5a1 1 0 0 1-.25 1z" /></svg>
      </button>
      <button onClick={onMore} aria-expanded={moreOpen} aria-label="More" className={`${btn} ${moreOpen ? "bg-pink-300 text-blue-950" : "bg-white/15 text-white"}`} data-testid="more-toggle">
        <svg viewBox="0 0 24 24" className="h-6 w-6" fill="currentColor"><circle cx="5" cy="12" r="2" /><circle cx="12" cy="12" r="2" /><circle cx="19" cy="12" r="2" /></svg>
      </button>
    </div>
  );
}
