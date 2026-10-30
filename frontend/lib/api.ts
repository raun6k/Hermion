// All REST calls (docs/api.md). Each pane uses these; panes never share client state.
import { API_URL } from "./config";
import type {
  ApiErrorBody,
  ExitResponse,
  Health,
  MerchantProfile,
  Product,
  SessionCreate,
  SessionCreated,
} from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "content-type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    const body = (await res.json().catch(() => null)) as ApiErrorBody | null;
    throw new ApiError(res.status, body?.error.code ?? "HTTP_ERROR", body?.error.message ?? res.statusText);
  }
  return (res.status === 204 ? undefined : await res.json()) as T;
}

export const api = {
  health: () => request<Health>("/health"),
  // customer
  createSession: (body: SessionCreate) =>
    request<SessionCreated>("/sessions", { method: "POST", body: JSON.stringify(body) }),
  exitSession: (id: string) => request<ExitResponse>(`/sessions/${id}/exit`, { method: "POST" }),
  // merchant
  merchant: () => request<MerchantProfile>("/merchant"),
  products: () => request<Product[]>("/merchant/products"),
  ttsTestUrl: (lang: "te-IN" | "hi-IN") => `${API_URL}/dev/tts-test?lang=${lang}`,
};
