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
- Token is pasted by the user at runtime into a landing screen (spec §9) and stored in `localStorage` under `nutribrain:token` (see `src/lib/tokenStore.ts`) — not a build-time env var.
- Fetch client/interceptor (`src/lib/apiClient.ts`) attaches `Authorization: Bearer <token>` to API requests.
- A 401 response clears the stored token and returns the user to the paste screen with an invalid-token message.
- Never log the token, even masked forms in debug output.

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
