from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastmcp import FastMCP

from app import settings as settings_module
from app.auth import AuthMiddleware

mcp = FastMCP("nutribrain")
mcp_app = mcp.http_app(path="/mcp")

app = FastAPI(title="nutribrain", lifespan=mcp_app.lifespan)

# Added last so it sits outermost and handles CORS preflight (OPTIONS, sent
# without an Authorization header) before AuthMiddleware ever sees it.
app.add_middleware(AuthMiddleware, token=settings_module.settings.app_token)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings_module.settings.cors_origin],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# Mounted last: Mount("/", ...) matches every path, so routes defined above it
# (like /health) must be registered first or the mount would shadow them.
app.mount("/", mcp_app)
