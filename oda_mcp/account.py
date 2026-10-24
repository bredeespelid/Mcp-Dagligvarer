"""Overføring av handlekurven til brukerens egen Oda-konto (eksperimentelt).

Oda har ikke et offisielt, åpent API for handlekurv. Dette bruker de samme kallene som
oda.com selv gjør (innlogging med e-post og passord, så POST til /cart/items/), og kan
slutte å virke hvis Oda endrer nettsiden.
"""

from __future__ import annotations

import http.cookiejar
import json
import os
import urllib.error
import urllib.request

from .catalog import BASE_URL, TIMEOUT, WEB_URL


class OdaAccountError(RuntimeError):
    pass


class OdaAccount:
    def __init__(self, email: str | None = None, password: str | None = None):
        self.email = email or os.environ.get("ODA_EMAIL")
        self.password = password or os.environ.get("ODA_PASSWORD")
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.logged_in = False

    @property
    def configured(self) -> bool:
        return bool(self.email and self.password)

    def _csrf(self) -> str:
        return next((c.value for c in self.jar if c.name == "csrftoken"), "")

    def _request(self, method: str, path: str, body: dict | None = None) -> dict:
        req = urllib.request.Request(
            f"{BASE_URL}{path}",
            method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "oda-mcp/0.1",
                "Referer": f"{WEB_URL}/no/",
                "X-CSRFToken": self._csrf(),
            },
        )
        try:
            with self.opener.open(req, timeout=TIMEOUT) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as e:
            raise OdaAccountError(f"Oda svarte {e.code} på {method} {path}") from e
        return json.loads(raw) if raw else {}

    def login(self) -> None:
        if not self.configured:
            raise OdaAccountError("Sett ODA_EMAIL og ODA_PASSWORD for å bruke Oda-kontoen din")
        self.opener.open(f"{WEB_URL}/no/", timeout=TIMEOUT).read()  # henter csrftoken-cookie
        self._request("POST", "/user/login/", {"username": self.email, "password": self.password})
        self.logged_in = True

    def add_items(self, items: list[tuple[int, int]]) -> dict:
        """Legg (product_id, antall) i Oda-kurven og returner Odas kurv etterpå."""
        if not self.logged_in:
            self.login()
        self._request("POST", "/cart/items/", {
            "items": [{"product_id": pid, "quantity": qty} for pid, qty in items],
        })
        return self._request("GET", "/cart/")
