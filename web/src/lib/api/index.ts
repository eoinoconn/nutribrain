/**
 * Typed API client (T-071) — one module wrapping every `/api` endpoint.
 *
 * OpenAPI-generation vs hand-written types
 * -----------------------------------------
 * FastAPI exposes `/openapi.json` automatically, so generating types (e.g.
 * via `openapi-typescript`) was considered. Decision: hand-write the types
 * in `./types.ts` instead, because:
 *   - This is a single-developer project with ~20 endpoints across 6
 *     routers; the surface is small and changes infrequently (each change
 *     needs a matching domain function + migration anyway).
 *   - Generation would add a new devDependency plus a generation script,
 *     and wiring drift-detection into CI would need either a running API
 *     instance in the `web` CI job (which currently has no Postgres
 *     service and is gated separately from `api` by `paths-filter`) or a
 *     committed `openapi.json` snapshot to diff against — both add real
 *     CI complexity for a project whose CLAUDE.md explicitly asks to
 *     justify new dependencies.
 *   - Hand-written types let the client use camelCase field names
 *     matching docs/style.md's TypeScript conventions, whereas generated
 *     types would mirror the backend's snake_case JSON verbatim (or need
 *     a codegen post-processing step to rename, adding yet more moving
 *     parts).
 *   - Reading the actual Pydantic schemas directly (as this task
 *     instructed) is a one-time cost; keeping them in sync going forward
 *     is a normal part of adding an endpoint, same as adding a domain
 *     function.
 * If the endpoint surface grows substantially, revisit this — generation
 * becomes more attractive as hand-sync cost grows.
 */

export * from "./types";
export * from "./client";
