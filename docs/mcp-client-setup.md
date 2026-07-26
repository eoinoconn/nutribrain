# MCP Client Configuration

This guide covers connecting Claude to the NutriBrain MCP server — via Claude
Desktop (`mcp-remote`), Claude web/mobile (custom connector), and rotating tokens
when needed.

---

## Prerequisites

- A deployed NutriBrain API (e.g. `https://nutrition-api.onrender.com`)
- A valid `APP_TOKEN` (see [Token generation](#token-generation) below)
- Node.js 18+ installed locally (for `npx mcp-remote`)

---

## Token generation

Generate a token with ~256 bits of entropy:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Store the value:

| Environment | Where to store |
|---|---|
| Local dev | `api/.env` as `APP_TOKEN=<value>` |
| Production | Render → Environment → `APP_TOKEN` |

The same token authenticates both `/api/*` and `/mcp` endpoints.

---

## Claude Desktop (mcp-remote)

Claude Desktop connects to remote MCP servers via the
[`mcp-remote`](https://www.npmjs.com/package/mcp-remote) bridge. Add the
following to your Claude Desktop configuration file:

- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
- **Linux:** `~/.config/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "nutrition": {
      "command": "npx",
      "args": [
        "mcp-remote",
        "https://nutrition-api.onrender.com/mcp",
        "--header",
        "Authorization: ******"
      ]
    }
  }
}
```

Replace `<YOUR_APP_TOKEN>` with the token stored in your deployment environment.

### How it works

1. Claude Desktop spawns `npx mcp-remote` as a local stdio process.
2. `mcp-remote` opens an HTTP connection to the remote `/mcp` endpoint.
3. Every request includes the `Authorization: ****** header.
4. The NutriBrain `AuthMiddleware` validates the token before the request
   reaches the MCP session layer.

### Verifying the connection

After saving the config and restarting Claude Desktop, open a new conversation
and confirm the tools are available:

> "What tools do you have for nutrition tracking?"

Claude should list tools like `log_meal`, `get_day`, `find_food`, etc.

---

## Claude web / mobile (custom connector)

For Claude on the web or mobile apps, use a **custom connector** instead of the
local `mcp-remote` bridge.

### Setup steps

1. Open Claude settings → **Connectors** (or **MCP Servers**, depending on
   platform version).
2. Select **Add custom connector**.
3. Fill in the fields:

| Field | Value |
|---|---|
| Name | `NutriBrain` |
| Server URL | `https://nutrition-api.onrender.com/mcp` |
| Authentication | Header-based |
| Header name | `Authorization` |
| Header value | `****** |

4. Save and verify — start a conversation and ask Claude to list available
   nutrition tools.

### Notes

- The server URL must include the `/mcp` path.
- The connector stores the token in Claude's account settings (encrypted
  at rest by Anthropic).
- If the API returns 401, Claude will surface a connection error — see
  [Troubleshooting](#troubleshooting) below.

---

## Token rotation

Rotate the token periodically or immediately if you suspect compromise.

### Steps

1. **Generate a new token:**

   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

2. **Update the server environment:**
   - Render: Dashboard → `nutrition-api` → Environment → update `APP_TOKEN` →
     save. The service restarts automatically.
   - Local: update `APP_TOKEN` in `api/.env` and restart the dev server.

3. **Update Claude Desktop config:**
   - Edit `claude_desktop_config.json` — replace the old token in the
     `Authorization` header value.
   - Restart Claude Desktop.

4. **Update Claude web/mobile connector:**
   - Open Claude settings → Connectors → `NutriBrain` → edit.
   - Replace the header value with `******
   - Save.

5. **Update the web dashboard:**
   - The dashboard will receive a 401 on the next request, automatically
     clearing the stored token and redirecting to the token-paste screen.
   - Paste the new token.

### Rotation checklist

- [ ] New token generated
- [ ] Server `APP_TOKEN` updated and service restarted
- [ ] Claude Desktop config updated and restarted
- [ ] Claude web/mobile connector updated
- [ ] Dashboard re-authenticated with new token

> **Tip:** Complete steps 2–5 in quick succession. Between updating the server
> and updating clients, existing sessions will fail with 401.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| 401 on every request | Token mismatch or missing `****** prefix | Verify the token matches `APP_TOKEN` on the server; ensure the header value starts with `****** (with a space) |
| `mcp-remote` not found | Node.js/npx not in PATH | Install Node.js 18+ and ensure `npx` is available |
| Connection timeout | Server not running or wrong URL | Verify the server is deployed; check the URL includes `/mcp` |
| Tools not listed in Claude | Config not loaded | Restart Claude Desktop; verify JSON syntax in config file |
| CORS errors (dashboard only) | Origin not in allowlist | Ensure the dashboard origin is listed in the server's CORS config |

---

## Security notes

- The token is a shared secret with full read/write access. Treat it like a
  password.
- Do not commit tokens to source control. Use environment variables or secret
  managers.
- The `AuthMiddleware` uses `hmac.compare_digest` for constant-time comparison,
  preventing timing attacks.
- `/health` is the only unauthenticated endpoint.
