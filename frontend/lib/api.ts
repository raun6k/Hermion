// All REST calls (docs/api.md). Each pane uses these; panes never share client state.
// With NEXT_PUBLIC_USE_MOCKS=true the same functions are served by mocks/backend.ts.
import { mockBackend } from "@/mocks/backend";
import { API_URL, USE_MOCKS } from "./config";
import { ApiError } from "./errors";
import type {
  ApiErrorBody,
  BasketEdit,
  BriefingResponse,
  ConfirmResponse,
  ExitResponse,
  Goal,
  Health,
  MandateConfirmResponse,
  MerchantBasket,
  MerchantPatch,
  MerchantProfile,
  Product,
  ProductCreate,
  ProductPatch,
  ReviewAction,
  ReviewResponse,
  SessionCreate,
  SessionCreated,
  SessionPublic,
  SessionSummary,
  SessionTrace,
  Stats,
} from "./types";

export { ApiError };

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "content-type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    const body = (await res.json().catch(() => null)) as ApiErrorBody | null;
    throw new ApiError(
      res.status,
      body?.error.code ?? "HTTP_ERROR",
      body?.error.message ?? res.statusText,
      body?.error.field ?? null,
    );
  }
  return (res.status === 204 ? undefined : await res.json()) as T;
}

const json = (body: unknown) => JSON.stringify(body);
const send = <T>(method: string, path: string, body?: unknown) =>
  request<T>(path, { method, body: body === undefined ? undefined : json(body) });

// Mock mode: run the call against the in-browser backend, after a beat so loading states show.
function mocked<T>(fn: () => T): Promise<T> {
  return new Promise((resolve, reject) =>
    setTimeout(() => {
      try {
        resolve(fn());
      } catch (e) {
        reject(e);
      }
    }, 120),
  );
}

const real = {
  health: () => request<Health>("/health"),
  // customer
  createSession: (body: SessionCreate) => send<SessionCreated>("POST", "/sessions", body),
  session: (id: string) => request<SessionPublic>(`/sessions/${id}`),
  confirm: (id: string) => send<ConfirmResponse>("POST", `/sessions/${id}/confirm`),
  exitSession: (id: string) => send<ExitResponse>("POST", `/sessions/${id}/exit`),
  // merchant
  merchant: () => request<MerchantProfile>("/merchant"),
  patchMerchant: (body: MerchantPatch) => send<MerchantProfile>("PATCH", "/merchant", body),
  products: () => request<Product[]>("/merchant/products"),
  createProduct: (body: ProductCreate) => send<Product>("POST", "/merchant/products", body),
  patchProduct: (id: string, body: ProductPatch) => send<Product>("PATCH", `/merchant/products/${id}`, body),
  deleteProduct: (id: string) => send<void>("DELETE", `/merchant/products/${id}`),
  goals: () => request<Goal[]>("/merchant/goals"),
  replaceGoals: (goals: Goal[]) => send<Goal[]>("PUT", "/merchant/goals", goals),
  sessions: (scope: "live" | "past") => request<SessionSummary[]>(`/merchant/sessions?scope=${scope}`),
  trace: (id: string) => request<SessionTrace>(`/merchant/sessions/${id}`),
  review: (id: string, action: ReviewAction) => send<ReviewResponse>("POST", `/merchant/sessions/${id}/review`, { action }),
  briefing: (id: string, text: string) => send<BriefingResponse>("POST", `/merchant/sessions/${id}/briefing`, { text }),
  confirmMandate: (id: string, mandateId: string) =>
    send<MandateConfirmResponse>("POST", `/merchant/sessions/${id}/mandates/${mandateId}/confirm`),
  editBasket: (id: string, body: BasketEdit) => send<MerchantBasket>("PUT", `/merchant/sessions/${id}/basket`, body),
  stats: () => request<Stats>("/merchant/stats"),
  // Any supported code (backend app/languages.py), e.g. the shop's first customer language.
  ttsTestUrl: (lang: string) => `${API_URL}/dev/tts-test?lang=${encodeURIComponent(lang)}`,
  ttsStreamUrl: (lang: string, text: string) =>
    `${API_URL}/dev/tts-stream?lang=${encodeURIComponent(lang)}&text=${encodeURIComponent(text)}`,
};

const fake: typeof real = {
  health: () => mocked(() => mockBackend().health()),
  createSession: (b) => mocked(() => mockBackend().createSession(b.qr_token, b.device_id)),
  session: (id) => mocked(() => mockBackend().publicSession(id)),
  confirm: (id) => mocked(() => mockBackend().confirm(id)),
  exitSession: (id) => mocked(() => mockBackend().exit(id)),
  merchant: () => mocked(() => mockBackend().getMerchant()),
  patchMerchant: (b) => mocked(() => mockBackend().patchMerchant(b)),
  products: () => mocked(() => mockBackend().listProducts()),
  createProduct: (b) => mocked(() => mockBackend().createProduct(b)),
  patchProduct: (id, b) => mocked(() => mockBackend().patchProduct(id, b)),
  deleteProduct: (id) => mocked(() => mockBackend().deleteProduct(id)),
  goals: () => mocked(() => mockBackend().listGoals()),
  replaceGoals: (g) => mocked(() => mockBackend().replaceGoals(g)),
  sessions: (scope) => mocked(() => mockBackend().listSessions(scope)),
  trace: (id) => mocked(() => mockBackend().trace(id)),
  review: (id, a) => mocked(() => mockBackend().review(id, a)),
  briefing: (id, t) => mocked(() => mockBackend().briefing(id, t)),
  confirmMandate: (id, m) => mocked(() => mockBackend().confirmMandate(id, m)),
  editBasket: (id, b) => mocked(() => mockBackend().editBasket(id, b)),
  stats: () => mocked(() => mockBackend().stats()),
  ttsTestUrl: real.ttsTestUrl,
  ttsStreamUrl: real.ttsStreamUrl,
};

export const api = USE_MOCKS ? fake : real;
