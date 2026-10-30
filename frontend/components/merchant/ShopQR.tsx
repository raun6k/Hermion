"use client";

// The shop's QR card, pinned bottom-right of the merchant pane. Visual only: the customer pane's camera
// finds it by `data-qr-target` and sends `qr_token` to POST /sessions (docs/frontend.md#drag-to-scan).
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

export function ShopQR({ token }: { token: string | null }) {
  const cells = useMemo(() => (token ? matrix(token) : null), [token]);
  return (
    <aside
      className="pointer-events-none absolute bottom-4 right-4 w-44 rounded-xl border border-slate-200 bg-white p-3 shadow-lg"
      data-testid="shop-qr"
    >
      <p className="mb-2 text-center text-xs font-medium text-slate-700">Scan to bargain with Hermion</p>
      {cells ? (
        <svg
          viewBox={`0 0 ${SIZE} ${SIZE}`}
          className="mx-auto h-32 w-32"
          shapeRendering="crispEdges"
          data-qr-target
          data-qr-token={token ?? ""}
          role="img"
          aria-label="Shop QR code"
        >
          <rect width={SIZE} height={SIZE} fill="#fff" />
          {cells.flatMap((row, y) => row.map((on, x) => (on ? <rect key={`${x}-${y}`} x={x} y={y} width="1" height="1" fill="#0f172a" /> : null)))}
        </svg>
      ) : (
        <div className="mx-auto h-32 w-32 animate-pulse rounded bg-slate-100" />
      )}
    </aside>
  );
}
