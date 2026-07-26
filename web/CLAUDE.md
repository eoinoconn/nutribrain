# Web Agent Guide

## Scope
This folder contains the React dashboard. It consumes `/api` endpoints only.

## Query Key Conventions (TanStack Query)
- Use tuple keys with stable prefixes.
- Suggested baseline:
  - `['day', localDate]`
  - `['meals', localDate]`
  - `['targets', localDate]`
  - `['foods', filters]`
  - `['templates']`
- Keep key factories in one module to prevent key drift.

## Optimistic Update Pattern (with rollback)
Use this pattern for mutations that update visible daily data:
1. `cancelQueries` for affected keys.
2. Snapshot previous cache values.
3. Apply optimistic cache update.
4. Call the mutation.
5. On error, restore the snapshot.
6. On settle, `invalidateQueries` for authoritative re-fetch.

## Auth Token Handling
- Token source is `APP_TOKEN`.
- Token should be provided via environment-backed config (for example `VITE_APP_TOKEN` in local setup) and never hardcoded.
- Fetch client/interceptor attaches `Authorization: Bearer <token>` to API requests.
- Never log the token.

## Accessibility Floor
- Keep `eslint-plugin-jsx-a11y` enabled and clean.
- Every form control requires an accessible label.
- Keyboard navigation must work for all interactive controls.
- Preserve visible focus indication.
- Color is never the sole way to convey state.

## Web Commands
- Install deps: `npm ci`
- Dev server: `npm run dev -- --host --port 5173`
- Tests: `npm run test`
- Lint: `npm run lint`
- Typecheck: `npx tsc -b`
- Build: `npm run build`
