// All REST calls (docs/api.md). Each pane uses these; panes never share client state.
// With NEXT_PUBLIC_USE_MOCKS=true the same functions are served by mocks/backend.ts.
import { mockBackend } from "@/mocks/backend";
import { API_URL, USE_MOCKS } from "./config";
import { ApiError } from "./errors";
import type {
  ApiErrorBody,
  BasketEdit,
  BasketPublic,
  BriefingResponse,
  ConfirmResponse,
  ExitResponse,
  Goal,
  Health,
  MandateConfirmResponse,
  MerchantBasket,
  MerchantChoice,
  PriceCheckAction,
  ProductPublic,
  SessionState,
  VisitPublic,
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
  ShopPublic,
  SessionSummary,
  SessionTrace,
  Stats,
} from "./types";

export { ApiError };

// Demo-only shop switch: the dashboard sends the chosen shop on every request (docs/api.md).
let merchantId: string | null = null;
export function setMerchantId(id: string | null) {
  merchantId = id;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "content-type": "application/json", ...(merchantId ? { "x-merchant-id": merchantId } : {}), ...init?.headers },
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
  shop: (qrToken?: string) => request<ShopPublic>(qrToken ? `/shop?qr_token=${encodeURIComponent(qrToken)}` : "/shop"),
  merchants: () => request<MerchantChoice[]>("/merchants"),
  shopProducts: (qrToken?: string) => request<ProductPublic[]>(qrToken ? `/shop/products?qr_token=${encodeURIComponent(qrToken)}` : "/shop/products"),
  removeFromBasket: (id: string, productId: string) => send<BasketPublic>("DELETE", `/sessions/${id}/basket/${encodeURIComponent(productId)}`),
  createSession: (body: SessionCreate) => send<SessionCreated>("POST", "/sessions", body),
  session: (id: string) => request<SessionPublic>(`/sessions/${id}`),
  confirm: (id: string) => send<ConfirmResponse>("POST", `/sessions/${id}/confirm`),
  exitSession: (id: string) => send<ExitResponse>("POST", `/sessions/${id}/exit`),
  // The shop home page: this device's recent baskets at the shop; rejoin = Talk to Hermion again.
  visits: (qrToken: string, deviceId: string) =>
    request<VisitPublic[]>(`/sessions/visits?qr_token=${encodeURIComponent(qrToken)}&device_id=${encodeURIComponent(deviceId)}`),
  rejoin: (id: string) => send<{ state: SessionState }>("POST", `/sessions/${id}/rejoin`),
  // merchant
  merchant: () => request<MerchantProfile>("/merchant"),
  patchMerchant: (body: MerchantPatch) => send<MerchantProfile>("PATCH", "/merchant", body),
  products: () => request<Product[]>("/merchant/products"),
  createProduct: (body: ProductCreate) => send<Product>("POST", "/merchant/products", body),
  patchProduct: (id: string, body: ProductPatch) => send<Product>("PATCH", `/merchant/products/${id}`, body),
  deleteProduct: (id: string) => send<void>("DELETE", `/merchant/products/${id}`),
  goals: (id?: string | null) => request<Goal[]>("/merchant/goals", id ? { headers: { "x-merchant-id": id } } : undefined),
  replaceGoals: (goals: Goal[]) => send<Goal[]>("PUT", "/merchant/goals", goals),
  sessions: (scope: "live" | "past") => request<SessionSummary[]>(`/merchant/sessions?scope=${scope}`),
  trace: (id: string) => request<SessionTrace>(`/merchant/sessions/${id}`),
  review: (id: string, action: ReviewAction) => send<ReviewResponse>("POST", `/merchant/sessions/${id}/review`, { action }),
  briefing: (id: string, text: string) => send<BriefingResponse>("POST", `/merchant/sessions/${id}/briefing`, { text }),
  confirmMandate: (id: string, mandateId: string) =>
    send<MandateConfirmResponse>("POST", `/merchant/sessions/${id}/mandates/${mandateId}/confirm`),
  editBasket: (id: string, body: BasketEdit) => send<MerchantBasket>("PUT", `/merchant/sessions/${id}/basket`, body),
  answerPriceCheck: (id: string, action: PriceCheckAction, price?: string) =>
    send<ReviewResponse>("POST", `/merchant/sessions/${id}/price-check`, { action, price }),
  stats: (days?: number) => request<Stats>(days ? `/merchant/stats?days=${days}` : "/merchant/stats"),
  // Any supported code (backend app/languages.py), e.g. the shop's first customer language.
  ttsTestUrl: (lang: string) => `${API_URL}/dev/tts-test?lang=${encodeURIComponent(lang)}`,
  ttsStreamUrl: (lang: string, text: string) =>
    `${API_URL}/dev/tts-stream?lang=${encodeURIComponent(lang)}&text=${encodeURIComponent(text)}`,
};

const fake: typeof real = {
  health: () => mocked(() => mockBackend().health()),
  shop: (qr) => mocked(() => mockBackend().publicShop(qr)),
  merchants: () => mocked(() => mockBackend().listMerchants()),
  shopProducts: () => mocked(() => mockBackend().shopProducts()),
  removeFromBasket: (id, pid) => mocked(() => mockBackend().removeFromBasket(id, pid)),
  answerPriceCheck: (id, action, price) => mocked(() => mockBackend().answerPriceCheck(id, action, price)),
  createSession: (b) => mocked(() => mockBackend().createSession(b.qr_token, b.device_id, b.customer_name)),
  session: (id) => mocked(() => mockBackend().publicSession(id)),
  confirm: (id) => mocked(() => mockBackend().confirm(id)),
  exitSession: (id) => mocked(() => mockBackend().exit(id)),
  visits: (qr, deviceId) => mocked(() => mockBackend().visits(qr, deviceId)),
  rejoin: (id) => mocked(() => mockBackend().rejoin(id)),
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
