# NutriBrain — Specification amendments and decisions

This document records resolutions to ambiguities in the spec, plus amendments that override the original text where they diverge. These decisions were made before implementation began and must not be revisited without substantial justification.

---

## Amendments (G1–G7)

Resolved in T-007. When the spec text contradicts an amendment below, this section wins.

### G1 — Soft-delete columns on `foods` and `templates`

Add `deleted_at timestamptz nullable` to both `foods` and `templates` tables.

**Semantics:**
- Every read path (queries, MCP tools) filters `deleted_at IS NULL`
- Hard delete is never used; soft delete preserves historical `meal_items` that reference deleted foods or templates
- Past meals logged from a deleted template remain in the history, still readable and editable

**Rationale:** Historical integrity. A meal logged six months ago should not become corrupted if a template or food is later removed.

---

### G2 — Tool surface count is 17, not 15

The spec's count in §4 treats `create_template`, `update_template`, `delete_template` and `delete_meal`, `delete_meal_item` as single entries (counting bullet headings).

**Correction:** Build all 17 distinct tools. Update §4 prose to reflect the accurate count.

---

### G3 — `last_logged_at` and `logged_count` are computed, not stored

The `find_food` tool returns both `last_logged_at` and `logged_count` as part of the food search response.

**Implementation:**
- These fields are computed in-query via a join to `meal_items` → `meals`
- Do **not** add columns to the `foods` table
- Do **not** maintain counters on meal insert/delete

**Rationale:** Stored counters drift silently with every schema change or backfill, corrupting the resolution rules in §3. At single-user scale, the join is free and the code is simpler and more obviously correct.

---

### G4 — Extended unit set with per-food density

**Quantity units expand per G4:**

- **On `meal_items.quantity_unit` and `template_items.quantity_unit`:** `g`, `kg`, `oz`, `lb`, `ml`, `l`, `fl_oz`, `tsp`, `tbsp`, `cup`, `piece`, `serving` (12 units)
- **On `foods.serving_unit`:** stays `g`, `ml`, `piece` (3 units) — the immutable reference unit
  - The `add_food` endpoint normalises an incoming label serving ("1 cup" of rice) into `ml` before storing
  - Widening this set would multiply the immutability problem with no benefit

**New column:** `foods.density_g_per_ml numeric nullable`
- Null means 1.0, preserving the current naive `g` ≡ `ml` behaviour
- Set per food for volume-to-mass conversion (e.g., rice ≈ 0.78, oil ≈ 0.92)
- The conversion factors are a single frozen constant in the domain layer, not a table

**Rationale:** Mass units (`g`, `kg`, `oz`, `lb`) convert by fixed factors. Volume units (`ml`, `l`, `fl_oz`, `tsp`, `tbsp`, `cup`) convert to millilitres by fixed factor, then to grams via density. Food-specific density is essential: a cup of uncooked rice is ~185 g, a cup of water ~237 g. Without it, adding `cup` makes the existing `g` ≡ `ml` simplification visibly wrong rather than silently wrong.

**Postgres enums:** Define all 12 values on `quantity_unit` enums from the outset. Adding enum values is easy; removing them is painful. This list is deliberately complete.

---

### G5 — Override provenance on `intervals_calories_out`

Add `intervals_calories_out.source enum('sync','manual')` with default `sync`.

**Semantics:**
- The sync worker (cron) writes `sync` and overwrites manual values by design (§8)
- The dashboard may hand-override calories-out; these write `manual`
- The UI shows which days were hand-set

**Rationale:** Distinguishes synced truth from user override, so the dashboard can signal "this is not from intervals.icu."

---

### G6 — Neon connection pool settings

Connection pooling on `SQLAlchemy.create_engine()`:
```python
pool_pre_ping=True,   # Verify connection before reuse
pool_recycle=300,     # Recycle connections after 5 minutes
pool_size=2           # 2 connections per process
```

**Rationale:** Neon's scale-to-zero closes idle connections. SQLAlchemy must not attempt to reuse a stale one. No keep-alive ping beyond the `pool_pre_ping`; cold starts are accepted on the low-traffic Starter plan.

**Additional deployment note:** Set `compute_units: 0.25` in `render.yaml` to enable scale-to-zero and keep run costs minimal.

---

### G7 — FastMCP auth inheritance is not automatic

**Critical security finding:**

FastAPI's `dependencies=[Depends(require_auth)]` on a router **does not** apply to mounted ASGI sub-applications. FastAPI only runs dependencies for routes it owns. A mounted ASGI app (including FastMCP) receives the request directly after the ASGI middleware layer, bypassing FastAPI's dependency machinery entirely.

**Consequence if missed:** If `/mcp` does not independently verify the `Authorization` header, every write tool is exposed unauthenticated on the public internet. The failure is silent — your own client sends the header, so you won't notice in testing.

**Required verification (T-030):** A test request to `/mcp` with **no** `Authorization` header must be rejected with 401. If it is not rejected, the auth check must move into ASGI middleware that wraps both the FastAPI app and the FastMCP mount.

---

## Questions and future amendments

### D-004 — Frontend token localStorage key: spec wins over backlog task text (2026-07-27)

**Conflict:** backlog task T-070's own text specified the token localStorage
key as `nutrition:token`. Spec §9 ("Dashboard UX") specifies `nutribrain:token`.
This backlog's own working agreement states that where the backlog and spec
disagree, the spec wins.

**Decision:** use `nutribrain:token` (per spec §9), implemented in
`web/src/lib/tokenStore.ts` as `TOKEN_STORAGE_KEY`. The backlog task text's
`nutrition:token` was treated as a transcription slip, not an intentional
override.

**Related correction:** `web/CLAUDE.md`'s "Auth Token Handling" section
previously described a build-time `VITE_APP_TOKEN` env var, which does not
match spec §9's runtime paste-token-into-`localStorage` flow (what T-070
actually implements). Corrected in the same change so future agents aren't
misled by it.

### D-003 — G7 resolved: auth enforced via ASGI middleware (2026-07-26)

**Empirical result (T-030):** confirmed G7's prediction. A `require_auth`
FastAPI dependency applied via `dependencies=[Depends(require_auth)]` on a
router does not run for requests handled by the FastMCP app mounted at
`/mcp` — `TestClient(app).post("/mcp", ...)` with no `Authorization` header
reached the MCP session layer unrejected in a throwaway reproduction.

**Decision:** auth is enforced by `AuthMiddleware` (`api/app/auth.py`), a
plain ASGI middleware added to the FastAPI app with `add_middleware`. It
wraps the entire ASGI stack — both FastAPI-owned routes and the mounted
FastMCP app — checking every request path except `/health` for a valid
`Authorization: Bearer <token>` header via `hmac.compare_digest`.

**Amendment to §9's "Forward-compatibility" and "Auth upgrade path":** spec
§9 names `require_auth` as "the seam for future Google OAuth ... zero route
code touched during upgrade," on the assumption every route declares
`Depends(require_auth)`. That assumption is false in this design — no route
does, and one at `/mcp` couldn't anyway. A `require_auth` function was
written and then removed: nothing called it, so it enforced nothing and
would have sat on routes as a misleading no-op. The upgrade seam is instead
`_auth_error` in `api/app/auth.py` — swap its body for session-cookie or JWT
validation and every route stays covered, because `AuthMiddleware` is what
every request actually passes through.

**Middleware ordering:** `CORSMiddleware` is added after `AuthMiddleware`
(Starlette runs middleware in reverse-add order, outermost last-added), so
browser CORS preflight `OPTIONS` requests — sent without an `Authorization`
header — are handled by `CORSMiddleware` before they ever reach the auth
check.

### D-002 — Fuzzy food-match similarity threshold (2026-07-26)

**Decision:** `resolve_food` uses a trigram similarity threshold of `0.35` via
`pg_trgm` (`similarity(lower(foods.name), lower(query)) >= 0.35`).

**Why this value:**
- It accepts common minor typos and punctuation drift (`"brennan bagel"` vs
  `"Brennans Bagel"`) without requiring exact tokenization.
- It avoids broad, low-quality matches that trigger accidental auto-selection
  and therefore violate the ambiguity-escalation rule.

**Implementation notes:**
- Resolution first attempts exact case-insensitive equality using
  `lower(name)` (aligned with `ix_foods_lower_name`), then applies trigram
  matching with the threshold above.
- Soft-deleted foods (`deleted_at IS NOT NULL`) are excluded from every
  candidate query.

### D-001 — Production image must provide `libpq` (2026-07-26)

**Context:** The runtime dependency is plain `psycopg` (pure-Python implementation), pinned in `api/uv.lock`. That implementation links against the system `libpq` shared library at runtime; it does **not** bundle one.

**Decision:**
- The production image **must** provide `libpq` (e.g. `apt-get install -y libpq5` on a Debian/`slim` base). Render's native Python runtime already includes it; a custom Docker base does not.
- Alternative if a system `libpq` is undesirable: switch the production dependency to `psycopg[c]` (compiled against system libpq, needs `libpq-dev` at build time) or `psycopg[binary]` (bundles libpq — discouraged by the psycopg maintainers for production because the bundled OpenSSL can't be patched independently).
- **Local dev / CI:** install system `libpq5` to mirror the production code path. Do not add `psycopg[binary]` to the manifest, to avoid dev/prod divergence.

**Action when deploy config lands:** Fold this requirement into `render.yaml` / the Dockerfile as part of the deployment task so the connection layer isn't broken at first boot.

**Rationale:** `render.yaml` is still a placeholder, so nothing currently guarantees `libpq` in production. Recording this now prevents a silent first-boot failure (`ImportError`/`libpq` not found) when the image is finally defined.
