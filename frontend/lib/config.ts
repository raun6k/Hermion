// NEXT_PUBLIC_* values are inlined at build time.
export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
export const WS_URL = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000";
export const USE_MOCKS = process.env.NEXT_PUBLIC_USE_MOCKS === "true";
// Demo shop's QR token; the drag-to-scan feature will read it from GET /merchant.
export const DEMO_QR_TOKEN = "hermion-m001-demo";
// Language for the dev TTS test clip only (demo customer); the product takes languages from shop data.
export const DEMO_CUSTOMER_LANGUAGE = "te-IN";
