# Hermion

A negotiation agent owned by the merchant, for small Indian shops. A customer bargains with Hermion by voice or keypad, a deterministic engine sets every price, and the merchant has the final call. Built for the Paytm Build for India AI Hackathon.

**Status:** Stage 1 done: engine, services and REST, agent building blocks, voice adapters and both UI panes (on mocks) are built and tested. The agent tool loop and text integration are Stage 2.

## Stack

- **Frontend:** Next.js 16, TypeScript, Tailwind. One page with two panes: merchant console on the left, customer phone on the right.
- **Backend:** FastAPI, Pydantic v2, SQLAlchemy 2 (async), Alembic, PostgreSQL 16.
- **LLM:** `openai/gpt-6-luna` through OpenRouter.
- **Voice:** Sarvam `saaras:v3-realtime` for speech-to-text and `bulbul:v4-flash` for text-to-speech.

## Run it

You need Docker. For local development you also need [uv](https://docs.astral.sh/uv/) and Node 20+ with pnpm 10 (`corepack enable pnpm`).

```bash
cp .env.example .env        # then fill in the API keys, or set USE_FAKE_LLM / USE_FAKE_SPEECH to true
make up                     # postgres + backend :8000 + frontend :3000, migrated and seeded
```

Open http://localhost:3000. Backend health is at http://localhost:8000/health.

If port 3000 is taken, start it with `FRONTEND_PORT=3002 make up`.

### Hot-reload dev

```bash
make install
make dev                    # postgres in Docker; backend + frontend run locally with reload
```

### Checks

```bash
make test                   # backend pytest + ruff, frontend typecheck + lint (offline, fake LLM/speech)
make e2e                    # Playwright: customer -> backend -> LLM -> merchant trace
make smoke                  # live OpenRouter + Sarvam calls (needs keys, costs credits)
```

To build the UI without a backend, set `NEXT_PUBLIC_USE_MOCKS=true`. The frontend then replays `frontend/mocks/` instead of calling the API.

## Layout

```text
backend/   FastAPI app (app/), Alembic migrations, seed data, tests, smoke script
frontend/  Next.js app: components/{merchant,customer}, lib/ (types, api, ws, audio), mocks/, e2e/
```

Design docs live in `docs/` and the agent guide in `AGENTS.md`. Both are kept local and untracked.
