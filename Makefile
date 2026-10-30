# Hermion dev commands. See docs/build-plan.md#commands-makefile.
SHELL := /bin/bash
BACKEND := uv run --directory backend
FRONTEND := pnpm --dir frontend

.PHONY: help up down logs dev dev-backend dev-frontend db migrate seed test test-backend test-frontend lint smoke eval e2e install

help:  ## List targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-14s %s\n", $$1, $$2}'

install:  ## Install backend + frontend deps and Playwright browser
	cd backend && uv sync
	$(FRONTEND) install
	$(FRONTEND) exec playwright install chromium

up:  ## Build and start postgres + backend :8000 + frontend :3000 (override FRONTEND_PORT) in Docker
	docker compose up -d --build --wait
	@echo "Frontend: http://localhost:$${FRONTEND_PORT:-3000}  Backend: http://localhost:8000/health"

down:  ## Stop the Docker stack
	docker compose down

logs:  ## Tail Docker logs
	docker compose logs -f --tail=100

db:  ## Start only postgres in Docker
	docker compose up -d --wait postgres

dev: db migrate seed  ## Hot-reload dev: postgres in Docker, backend + frontend local
	$(MAKE) -j2 dev-backend dev-frontend

dev-backend:
	$(BACKEND) uvicorn app.main:app --reload --port 8000

dev-frontend:
	$(FRONTEND) dev

migrate: db  ## Alembic upgrade head
	$(BACKEND) alembic upgrade head

seed: db  ## Load backend/seed/ into the DB
	$(BACKEND) python -m app.seed

lint:  ## Ruff + ESLint
	$(BACKEND) ruff check .
	$(BACKEND) ruff format --check .
	$(FRONTEND) lint

test: test-backend test-frontend  ## All offline tests (fake LLM/speech)

test-backend: db
	$(BACKEND) ruff check .
	$(BACKEND) pytest -q

test-frontend:
	$(FRONTEND) typecheck
	$(FRONTEND) lint

e2e: db  ## Playwright: full slice through real backend (fake LLM) + frontend
	$(FRONTEND) e2e

smoke:  ## Live OpenRouter + Sarvam checks (needs keys, costs credits)
	$(BACKEND) python -m scripts.smoke

eval:  ## Agent scenario eval (Stage 2)
	@echo "Not built yet: tests/eval/run_scenarios.py arrives in Stage 2 (docs/build-plan.md)." && exit 1
