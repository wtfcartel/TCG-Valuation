"""GET /api/logout: clear the session cookie and return to the login page."""

from http.server import BaseHTTPRequestHandler


class handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(303)
        self.send_header("Location", "/login.html?out=1")
        self.send_header("Set-Cookie", "gt_session=; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=0")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
