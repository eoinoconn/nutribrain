# NutriBrain developer task runner.
#
# Mirrors the CI pipeline in .github/workflows/ci.yml so that `make check`
# locally runs the same gate CI enforces. Targets shell out into the api/ and
# web/ subprojects, which own their own toolchains (uv and npm respectively).
#
# Note: the `migrate*` targets and therefore `make check` need a reachable
# Postgres (DATABASE_URL in api/.env or the environment). Everything else runs
# without a database.

.DEFAULT_GOAL := help
SHELL := /bin/bash

.PHONY: help install install-api install-web \
	lint lint-api lint-web format \
	typecheck typecheck-api typecheck-web \
	test test-api test-web \
	migrate migrate-check build-web \
	check api-check web-check clean

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

## Install ---------------------------------------------------------------------
install: install-api install-web ## Install all dependencies

install-api: ## Install API dependencies
	cd api && uv sync --all-groups

install-web: ## Install web dependencies
	cd web && npm ci

## Lint / format ---------------------------------------------------------------
lint: lint-api lint-web ## Lint both projects

lint-api: ## Lint + format-check the API
	cd api && uv run ruff check . && uv run ruff format --check .

lint-web: ## Lint the web app
	cd web && npm run lint

format: ## Auto-format API code
	cd api && uv run ruff format .

## Typecheck -------------------------------------------------------------------
typecheck: typecheck-api typecheck-web ## Type-check both projects

typecheck-api: ## Type-check the API
	cd api && uv run mypy app

typecheck-web: ## Type-check the web app
	cd web && npx tsc -b

## Test ------------------------------------------------------------------------
test: test-api test-web ## Run all unit tests

test-api: ## Run API tests
	cd api && uv run pytest

test-web: ## Run web tests
	cd web && npm run test -- --run

## Migrations ------------------------------------------------------------------
migrate: ## Apply all migrations (needs DATABASE_URL)
	cd api && uv run alembic upgrade head

migrate-check: ## Apply migrations and assert models match (needs DATABASE_URL)
	cd api && uv run alembic upgrade head && uv run alembic check

## Build -----------------------------------------------------------------------
build-web: ## Production build of the web app
	cd web && npm run build

## Aggregate -------------------------------------------------------------------
check: api-check web-check ## Run the full CI gate locally

api-check: lint-api typecheck-api migrate-check test-api ## All API validations

web-check: lint-web typecheck-web test-web build-web ## All web validations

clean: ## Remove caches and build artifacts
	rm -rf api/.ruff_cache api/.pytest_cache api/.mypy_cache
	rm -rf web/dist web/node_modules/.vite
