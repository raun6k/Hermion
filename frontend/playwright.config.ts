import { defineConfig, devices } from "@playwright/test";

// E2E runs its own backend (fake LLM/speech, test DB) and frontends on spare ports, so it never collides
// with `make dev`. Two frontends: one against the real backend, one in mock mode (the scripted demo).
const API_PORT = 8001;
const WEB_PORT = 3101;
const MOCK_PORT = 3102;
const TEST_DB =
  process.env.TEST_DATABASE_URL ?? "postgresql+asyncpg://hermion:hermion@localhost:5432/hermion_test";
const desktop = { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } };

export default defineConfig({
  testDir: "./e2e",
  timeout: 45_000,
  retries: 0,
  workers: 1, // one shared backend/test DB
  use: { viewport: { width: 1440, height: 900 } },
  projects: [
    { name: "backend", testMatch: /skeleton\.spec\.ts|merchant\.spec\.ts/, use: { ...desktop, baseURL: `http://localhost:${WEB_PORT}` } },
    { name: "mocks", testMatch: /mock-demo\.spec\.ts/, use: { ...desktop, baseURL: `http://localhost:${MOCK_PORT}` } },
  ],
  webServer: [
    {
      command: `uv run sh -c "alembic upgrade head && python -m app.seed && uvicorn app.main:app --port ${API_PORT}"`,
      cwd: "../backend",
      url: `http://localhost:${API_PORT}/livez`,
      env: {
        DATABASE_URL: TEST_DB,
        USE_FAKE_LLM: "true",
        USE_FAKE_SPEECH: "true",
        CORS_ORIGINS: `http://localhost:${WEB_PORT}`,
      },
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: `pnpm build && pnpm start --port ${WEB_PORT}`,
      url: `http://localhost:${WEB_PORT}`,
      env: {
        NEXT_PUBLIC_API_URL: `http://localhost:${API_PORT}`,
        NEXT_PUBLIC_WS_URL: `ws://localhost:${API_PORT}`,
        NEXT_PUBLIC_USE_MOCKS: "false",
        NEXT_DIST_DIR: ".next-e2e",
      },
      reuseExistingServer: false,
      timeout: 180_000,
    },
    {
      command: `pnpm build && pnpm start --port ${MOCK_PORT}`,
      url: `http://localhost:${MOCK_PORT}`,
      env: { NEXT_PUBLIC_USE_MOCKS: "true", NEXT_DIST_DIR: ".next-mocks" },
      reuseExistingServer: false,
      timeout: 180_000,
    },
  ],
});
