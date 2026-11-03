"""POST /api/login: check the username and password against SITE_USERNAME / SITE_PASSWORD (Vercel environment
variables) and issue a signed session cookie that middleware.js verifies on every request. Standard library only."""

from __future__ import annotations

import hashlib
import hmac
import os
import time
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, quote

SESSION_HOURS = 8


def sign(secret: str, payload: str) -> str:
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def session_cookie(user: str, secret: str, now: float | None = None) -> str:
    exp = int((now or time.time()) + SESSION_HOURS * 3600)
    safe_user = "".join(c for c in user if c.isalnum() or c in "-_") or "user"
    return f"{safe_user}.{exp}.{sign(secret, f'{safe_user}.{exp}')}"


def safe_next(value: str) -> str:
    return value if value.startswith("/") and not value.startswith("//") and "\\" not in value else "/"


class handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        length = min(int(self.headers.get("Content-Length") or 0), 4096)
        form = parse_qs(self.rfile.read(length).decode("utf-8", "replace"))
        user = (form.get("username") or [""])[0].strip()
        password = (form.get("password") or [""])[0]
        nxt = safe_next((form.get("next") or ["/"])[0])
        want_user, want_pass = os.environ.get("SITE_USERNAME", ""), os.environ.get("SITE_PASSWORD", "")
        secret = os.environ.get("SESSION_SECRET", "")
        if not (want_user and want_pass and secret):
            return self._redirect("/login.html?e=setup")
        ok = hmac.compare_digest(user.lower().encode(), want_user.lower().encode()) & \
            hmac.compare_digest(password.encode(), want_pass.encode())
        if not ok:
            time.sleep(0.8)                      # slow down guessing
            return self._redirect(f"/login.html?e=1&next={quote(nxt)}")
        cookie = (f"gt_session={quote(session_cookie(user, secret))}; Path=/; HttpOnly; Secure; SameSite=Lax; "
                  f"Max-Age={SESSION_HOURS * 3600}")
        self._redirect(nxt, cookie)

    def do_GET(self) -> None:
        self._redirect("/login.html")

    def _redirect(self, location: str, cookie: str | None = None) -> None:
        self.send_response(303)
        self.send_header("Location", location)
        self.send_header("Cache-Control", "no-store")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
