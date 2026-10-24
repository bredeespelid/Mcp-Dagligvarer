"""Kjør serveren over HTTP (streamable-http), f.eks. på Render.

Settes MCP_AUTH_TOKEN, må klienter sende den som `Authorization: Bearer <token>` eller
som `?key=<token>` i URL-en (for klienter som bare tar imot en URL, som claude.ai).
"""

from __future__ import annotations

import hmac
import os
import urllib.parse

import uvicorn
from starlette.responses import JSONResponse

from .server import mcp


class TokenAuth:
    def __init__(self, app, token: str | None):
        self.app = app
        self.token = token

    def _authorized(self, scope) -> bool:
        headers = dict(scope.get("headers") or [])
        auth = headers.get(b"authorization", b"").decode()
        query = urllib.parse.parse_qs(scope.get("query_string", b"").decode())
        supplied = auth.removeprefix("Bearer ").strip() or (query.get("key") or [""])[0]
        return hmac.compare_digest(supplied, self.token)

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"] == "/healthz":
            return await JSONResponse({"status": "ok"})(scope, receive, send)
        if self.token and scope["type"] == "http" and not self._authorized(scope):
            return await JSONResponse({"error": "unauthorized"}, status_code=401)(scope, receive, send)
        await self.app(scope, receive, send)


def create_app():
    app = mcp.streamable_http_app(host="0.0.0.0", stateless_http=True)
    return TokenAuth(app, os.environ.get("MCP_AUTH_TOKEN"))


def main() -> None:
    uvicorn.run(create_app(), host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))


if __name__ == "__main__":
    main()
