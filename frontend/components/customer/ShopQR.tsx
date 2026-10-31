"use client";

// A shop's counter sign, shown above the phone in the customer half (the merchant pane has no QR). The
// draggable camera finds it by `data-qr-target` and sends `qr_token` to POST /sessions.
import { useMemo } from "react";

const SIZE = 25;

function matrix(token: string): boolean[][] {
  let h = 2166136261;
  const next = () => {
    for (let i = 0; i < token.length; i++) h = Math.imul(h ^ token.charCodeAt(i), 16777619);
    h = Math.imul(h ^ (h >>> 15), 2246822519);
    return (h >>> 0) / 4294967296;
  };
  const cells = Array.from({ length: SIZE }, () => Array.from({ length: SIZE }, () => next() > 0.52));
  const finder = (r: number, c: number) => {
    for (let y = -1; y <= 7; y++)
      for (let x = -1; x <= 7; x++) {
        const rr = r + y;
        const cc = c + x;
        if (rr < 0 || cc < 0 || rr >= SIZE || cc >= SIZE) continue;
        const ring = Math.max(Math.abs(y - 3), Math.abs(x - 3));
        cells[rr][cc] = y >= 0 && y <= 6 && x >= 0 && x <= 6 && ring !== 2;
      }
  };
  finder(0, 0);
  finder(0, SIZE - 7);
  finder(SIZE - 7, 0);
  return cells;
}

export function ShopQR({ token, label, onTap }: { token: string; label: string; onTap?: () => void }) {
  const cells = useMemo(() => matrix(token), [token]);
  return (
    <button
      type="button"
      onClick={onTap}
      className="w-[68px] min-w-0 shrink rounded-lg bg-white p-1 text-center shadow-sm"
      aria-label={`Scan ${label}`}
      data-testid={`shop-qr-${token}`}
    >
      <svg
        viewBox={`0 0 ${SIZE} ${SIZE}`}
        className="mx-auto h-11 w-11"
        shapeRendering="crispEdges"
        data-qr-target
        data-qr-token={token}
        role="img"
        aria-label={`${label} QR code`}
      >
        <rect width={SIZE} height={SIZE} fill="#fff" />
        {cells.flatMap((row, y) => row.map((on, x) => (on ? <rect key={`${x}-${y}`} x={x} y={y} width="1" height="1" fill="#0f172a" /> : null)))}
      </svg>
      <span className="block truncate text-[9px] font-medium text-slate-700">{label}</span>
    </button>
  );
}
