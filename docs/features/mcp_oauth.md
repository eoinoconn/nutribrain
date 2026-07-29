# Feature: OAuth for the MCP Server (Claude Web/Desktop Connector)

**Status:** proposed **Origin:** user request, 2026-07-29 — enable Claude's
web UI (and desktop app) to connect to NutriBrain's `/mcp` endpoint as a
custom connector **Touches:** `api/app/main.py`, `api/app/auth.py`,
`api/app/settings.py`, a new `api/app/mcp_auth/` module, one new Alembic
migration, `render.yaml`, `.env.example` **Record as:** the next sequential
`D-0NN` in `docs/decisions.md` once accepted.

---

## Motivation

Today `/mcp` (mounted at the app root — see `api/app/main.py:129`) is
protected by the same static bearer token as `/api` (`AuthMiddleware`,
`api/app/auth.py`). That works for tools you configure yourself (`curl`,
a local MCP client with the token in config), but Claude's web UI and
desktop app add remote MCP servers as **custom connectors**, and the MCP
spec requires those to authenticate via OAuth 2.1 with dynamic client
registration (DCR) and PKCE — there's no way to paste a static bearer
token into that flow. Without OAuth, Claude web/desktop cannot connect to
NutriBrain at all.

This is a single-user app (per `CLAUDE.md`: "no `user_id`, exactly one
user"), so the goal isn't a general-purpose auth system — it's the minimum
OAuth surface that satisfies the MCP connector requirement while only ever
authorizing one person: you.

---

## Current behavior

- `AuthMiddleware` (`api/app/auth.py`) wraps the entire ASGI stack —
  `/api/*` and the FastMCP mount at `/` alike — and requires
  `Authorization: Bearer <APP_TOKEN>` on every request except `/health`.
- `mcp = FastMCP("nutribrain")` (`api/app/main.py:92`) is constructed with
  no `auth=` provider; FastMCP itself does no authentication. The bearer
  check is the only gate, applied uniformly by the outer middleware.
- G7 (`docs/decisions.md` D-003) already established that per-route
  `Depends(...)` auth doesn't reach the FastMCP mount — enforcement has to
  wrap the whole ASGI stack or be handled inside FastMCP's own `auth=`
  mechanism. Any OAuth design must respect that finding.

---

## Proposed behavior

Give the FastMCP server its own OAuth provider, scoped to Google as the
identity provider, restricted to a single allow-listed email address (you).
`/api/*` keeps the existing static bearer token unchanged — this feature
touches the MCP mount only.

**Why Google, not a self-issued username/password AS:** FastMCP ships a
`GoogleProvider` (`fastmcp.server.auth.providers.google`) that implements
the full OAuth-proxy pattern already: it runs a real OAuth 2.1 authorization
server (DCR, PKCE, consent screen) in front of Google as the upstream IdP,
and exposes the authenticated user's verified email in the token claims.
That means no passwords to manage and no custom AS logic to get right for
a security-sensitive flow — just wire it up and allow-list one email.
Building a self-issued AS was considered and rejected: FastMCP also ships
an `InMemoryOAuthProvider`, but its own docstring says "for testing
purposes," and it holds all state in process memory — a Render restart
would silently log Claude out and force re-auth. Not acceptable for a
connector you expect to stay connected.

**Why not the default file-backed storage:** `GoogleProvider` persists its
proxy state (registered clients, encrypted tokens) via a pluggable
`client_storage: AsyncKeyValue`. Left at its default, that's an
encrypted file store under a local data directory — fine on a laptop, but
Render's filesystem is ephemeral across deploys and restarts, so every
deploy would silently revoke Claude's registration and force the OAuth
dance again. Postgres is already the one source of truth for this app
(`CLAUDE.md`), it's already provisioned, and it's the only storage that
survives a Render deploy — so `client_storage` should be a small
Postgres-backed `AsyncKeyValue` implementation, not a new backing store.

**Single-user enforcement:** `GoogleProvider`'s token verifier returns Google
account claims (`email`, `email_verified`, `sub`, ...) but doesn't itself
restrict *which* Google account may authenticate. A thin subclass
(or wrapping `TokenVerifier`) must reject any verified token whose `email`
claim isn't the one configured value — otherwise anyone with a Google
account could complete the consent screen and get a working MCP session.

**Scope of change:**
- New: `api/app/mcp_auth/` — the Postgres-backed `AsyncKeyValue` storage
  adapter and the email-allow-list wrapper around Google's token verifier.
- Changed: `api/app/main.py` — `FastMCP("nutribrain", auth=...)` gets the
  new provider; the mount no longer relies solely on the outer
  `AuthMiddleware` for `/mcp`.
- Changed: `api/app/auth.py` — `_UNPROTECTED_PREFIXES` (or equivalent) grows
  to exclude the paths FastMCP's OAuth provider serves itself
  (`/.well-known/oauth-authorization-server`, `/register`, `/authorize`,
  `/token`, the configured `redirect_path`) — those must be reachable
  *without* the static bearer token, since the whole point is that Claude
  doesn't have one yet when it starts the flow.
- Changed: `api/app/settings.py` — new required/optional settings (client
  ID/secret, allowed email, public base URL for redirect construction).
- New: one Alembic migration for the key-value storage table.
- Changed: `render.yaml`, `.env.example`, spec Appendix A.

**Out of scope:** no change to `/api/*` auth, no change to the MCP tool
surface itself, no multi-user support (the allow-list is exactly one email,
matching the single-user model — this is enforcement of that model, not a
step away from it).

---

## Open questions to resolve before starting

1. **Redirect path and public base URL.** `GoogleProvider(base_url=...)`
   must be NutriBrain's real public Render URL, and Google Cloud Console's
   OAuth client must have a matching authorized redirect URI
   (`{base_url}{redirect_path}`, default `/auth/callback`). These two must
   agree exactly or Google will reject the callback. Confirm the exact
   deployed URL before requesting the Google OAuth client.
2. **Consent screen (`require_authorization_consent`).** Default `True`
   shows a NutriBrain-branded consent screen before redirecting to Google.
   For a single-user app this is mostly ceremony, but leaving it on costs
   nothing and is the safer default — recommend keeping it `True` rather
   than special-casing it off.
3. **Required scopes — RESOLVED, `openid` alone is not enough.** The
   original recommendation here (`openid` alone, on the assumption `email`
   comes back via tokeninfo/userinfo regardless of granted scope) was wrong
   and reproduced live: with `required_scopes=["openid"]`, Google's
   tokeninfo/userinfo responses came back `200` but omitted a truthy
   `email_verified` claim, so every login — including the correct account —
   was rejected with `email_not_verified`. Fixed by requesting
   `required_scopes=["openid", "email"]`; still not requesting
   `userinfo.profile` since NutriBrain has no use for name/picture.

---

## Definition of done (applies to all tasks below)

Same bar as the main backlog: lint/typecheck/tests pass, docstrings on
public functions, PR description names which section of this doc it
implements. No new dependency beyond what `fastmcp` already ships
(`GoogleProvider`, `AsyncKeyValue` protocol) without justification.

---

## Phase 11 — MCP OAuth via Google

### F-101 · Postgres-backed `AsyncKeyValue` storage adapter
**Depends:** — **Owner: Claude**

- New module implementing the `key_value.aio.protocols.AsyncKeyValue`
  protocol backed by a single new table (e.g. `mcp_oauth_kv(collection,
  key, value, expires_at)`), matching whatever get/put/delete(+TTL) surface
  the protocol requires.
- New Alembic migration for that table. Follow existing migration
  conventions in `api/migrations`; never edit a merged one.
- Unit tests: round-trip a value, TTL expiry behaves, key/collection
  isolation.

**Done when:** the adapter passes a small conformance test exercising every
method `OAuthProxy`/`GoogleProvider` actually calls on `client_storage`.

---

### F-102 · Single-email allow-list wrapper around Google token verification
**Depends:** — **Parallel with:** F-101 **Owner: Claude**

- Wrap or subclass the verifier `GoogleProvider` uses so that a token whose
  `claims["email"]` doesn't case-insensitively match the one configured
  allowed email is treated as invalid (same rejection path as an
  unverified/expired token — don't leak *why* it was rejected beyond a log
  line).
- Also reject if `email_verified` is falsy — an unverified Google email
  shouldn't grant access.
- Unit tests: matching email passes, non-matching email is rejected,
  unverified email is rejected, case differences in the email are ignored.

**Done when:** a forged/foreign-account token with a valid Google signature
but the wrong email is rejected before it reaches any MCP tool.

---

### F-103 · Settings and wiring
**Depends:** F-101, F-102 **Owner: Claude**

- `api/app/settings.py`: add `google_oauth_client_id`,
  `google_oauth_client_secret`, `mcp_allowed_email`, `mcp_public_base_url`
  (or reuse an existing base-URL setting if one already exists for this
  purpose — check before adding a duplicate). Follow the existing
  fail-loudly-on-missing pattern for whichever of these are required in
  production.
- `api/app/main.py`: construct `GoogleProvider(client_id=..., client_secret=...,
  base_url=..., client_storage=<F-101 adapter>, required_scopes=["openid"])`,
  wrap its token verifier with F-102, and pass the result as
  `FastMCP("nutribrain", auth=...)`.
- `api/app/auth.py`: extend the unprotected-prefix allowlist to cover the
  OAuth-provider-served paths (well-known discovery, `/register`,
  `/authorize`, `/token`, the redirect path) so `AuthMiddleware`'s static
  bearer check doesn't shadow the OAuth handshake. Keep everything else
  (including the rest of `/mcp`'s actual tool-call traffic, which now
  authenticates via the Google-issued token instead) covered.
- Update `.env.example` and spec Appendix A with the new vars.

**Done when:** locally, a Google OAuth app with `redirect_uri =
http://localhost:8000/auth/callback` completes a full authorize→token
round trip against the dev server, and an unrecognized token on `/mcp`
still gets a 401.

---

### F-104 · Automated tests for the auth-decision surface
**Depends:** F-103 **Owner: Claude**

- Test that `/mcp`'s well-known/register/authorize/token paths are
  reachable without the static `APP_TOKEN` bearer header.
- Test that a request to `/mcp` with a valid-shaped-but-wrong-email token
  (mock the verifier, don't call real Google) is rejected.
- Test that `/api/*` behavior is completely unchanged (still requires the
  static bearer token, still 401s without it) — this is a regression
  guard, since it's easy to accidentally widen the unprotected-prefix set
  too far in F-103.

**Done when:** `uv run pytest` covers all three cases above and fails if
the prefix allowlist is ever widened past what F-103 intended.

---

### F-105 · Create the Google Cloud OAuth client
**Depends:** — **Owner: You** (external console, not code)

- In Google Cloud Console: create (or reuse) a project, configure the
  OAuth consent screen (can stay in "Testing" mode with yourself as the
  only test user — no Google verification review needed for a single-user
  app), and create an OAuth 2.0 Client ID of type "Web application."
- Authorized redirect URI: the exact `{deployed_base_url}/auth/callback`
  (confirm the deployed base URL first — see Open Question 1 above).
- Hand the resulting client ID and client secret to whichever secret store
  F-106 uses — don't paste them into a PR or commit them anywhere.

**Done when:** you have a client ID/secret pair and the redirect URI is
saved in the Google console entry.

---

### F-106 · Configure Render environment/secrets
**Depends:** F-103, F-105 **Owner: You**

- Add `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`,
  `MCP_ALLOWED_EMAIL` (your email), and the public base URL setting to the
  Render service's environment, marking the secret ones `sync: false` in
  `render.yaml` (Claude can add the `render.yaml` entries in F-103; only
  the actual secret values need to be pasted into the Render dashboard by
  you).
- Redeploy and confirm `/health` still returns 200 and `/api/*` still
  requires the existing bearer token (no regression from this change).

**Done when:** the deployed service starts cleanly with the new env vars
set and existing API/dashboard behavior is unaffected.

---

### F-107 · Connect Claude web/desktop as a custom connector
**Depends:** F-106 **Owner: You** (interactive browser flow — Claude cannot
drive Google's consent screen on your behalf)

- In Claude's connector settings, add a custom connector pointing at the
  deployed `/mcp` URL.
- Complete the Google sign-in/consent screen when prompted.
- Confirm Claude can list and call NutriBrain's MCP tools end to end (e.g.
  a read-only tool like `list_templates`) via the web UI.

**Done when:** Claude web UI successfully calls at least one NutriBrain MCP
tool using the OAuth-issued session, with no static token involved.

---

### F-108 · Revocation / offboarding path
**Depends:** F-107 **Owner: You**, doc by **Claude**

- Document (in this file's follow-up or `docs/decisions.md`) how to revoke
  Claude's access if needed: revoke the app's access from your Google
  Account's third-party access settings, which invalidates the upstream
  refresh token; F-101's storage entries for that client become orphaned
  and can be left to expire naturally or cleared manually.

**Done when:** the revocation steps are written down somewhere findable,
not just known implicitly.

---

## Out of scope

- No change to `/api/*` authentication or the existing static
  `APP_TOKEN` — the React dashboard keeps working exactly as it does today.
- No multi-user support of any kind. The allow-list is intentionally a
  single hardcoded email, not a user table.
- No support for MCP clients other than Google-authenticated ones (e.g. no
  parallel GitHub/username-password path) unless a future need arises.

## Parallelization

F-101 and F-102 have no dependency on each other and can run in parallel.
F-103 depends on both. F-104 depends on F-103. F-105 (Google console) has
no code dependency and can happen any time, but F-106 needs both F-103
(for the env var names/render.yaml entries) and F-105 (for the actual
values). F-107 needs F-106 deployed. F-108 is documentation and can trail
behind at any point after F-107.
