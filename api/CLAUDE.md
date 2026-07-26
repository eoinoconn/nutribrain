# API Agent Guide

## Scope
This folder contains the Python service for both HTTP API and MCP entry points. Domain behavior is authoritative and shared.

## Domain Layer Contract
- Business rules live in `app/domain/`.
- Domain functions accept primitives and typed DTOs, return typed DTOs, and raise domain exceptions.
- Domain code must not import FastAPI request/response types or FastMCP tool transport types.
- Routes and MCP tools only validate/translate inputs and outputs, then call domain functions.

## Exceptions
- Use one hierarchy rooted at `DomainError`.
- Every domain exception carries the Appendix C `error` code.
- Transport mapping (HTTP status codes / MCP tool errors) belongs in adapter code, not in the domain.

## Session and Transaction Boundaries
- Session lifecycle is owned by app wiring (dependency/middleware), not domain functions.
- Domain functions receive a session and perform deterministic work within that boundary.
- Prefer one request/tool invocation per transaction boundary.
- Roll back on domain or persistence errors; do not partially commit multi-step mutations.

## Alembic Workflow
- Never edit a merged migration.
- Create new revisions for every schema change: `uv run alembic revision --autogenerate -m "<message>"`.
- Apply migrations locally: `uv run alembic upgrade head`.
- Keep downgrade paths functional.

## MCP Tool Registration
- MCP tools are declared in `app/mcp/` and registered by app startup wiring.
- Each tool should call existing domain functions instead of introducing parallel logic.
- Keep tool schemas stable and explicit; map tool-level errors from domain exceptions.

## API Commands
- Install deps: `uv sync --all-groups`
- Dev server: `uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`
- Tests: `uv run pytest`
- Lint: `uv run ruff check . && uv run ruff format --check .`
- Typecheck: `uv run mypy app`
- Migrate: `uv run alembic upgrade head`
