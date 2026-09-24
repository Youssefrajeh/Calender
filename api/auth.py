"""Web sign-in for the hosted wallpaper (Google OAuth authorization-code flow).

GET /api/auth            -> redirects to Google
GET /api/auth?code=...   -> callback: exchanges the code and redirects to /?key=<refresh token>&setup=1

Requires a *Web application* OAuth client with redirect URI https://<your-domain>/api/auth.
"""
import json
import os
import secrets
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPE = "openid email profile https://www.googleapis.com/auth/calendar"


class handler(BaseHTTPRequestHandler):
    def _redirect(self, url, cookie=None):
        self.send_response(302)
        self.send_header("Location", url)
        self.send_header("Cache-Control", "no-store")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()

    def _page(self, msg):
        self.send_response(400)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(f"<h2 style='font-family:sans-serif'>{msg}</h2><a href='/'>Back</a>".encode())

    def do_GET(self):
        host = self.headers.get("X-Forwarded-Host") or self.headers.get("Host")
        redirect = f"https://{host}/api/auth"
        q = {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).items()}

        if "code" not in q and "error" not in q:  # start
            state = secrets.token_urlsafe(16)
            url = AUTH_URL + "?" + urllib.parse.urlencode({
                "client_id": os.environ["GOOGLE_CLIENT_ID"], "redirect_uri": redirect,
                "response_type": "code", "scope": SCOPE, "state": state,
                "access_type": "offline", "prompt": "consent"})
            return self._redirect(url, f"oauth_state={state}; HttpOnly; Secure; SameSite=Lax; Path=/api/auth; Max-Age=600")

        cookies = dict(c.strip().split("=", 1) for c in self.headers.get("Cookie", "").split(";") if "=" in c)
        if "error" in q or not q.get("state") or q.get("state") != cookies.get("oauth_state"):
            return self._page("Sign-in failed or was cancelled.")
        data = urllib.parse.urlencode({
            "client_id": os.environ["GOOGLE_CLIENT_ID"], "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
            "code": q["code"], "redirect_uri": redirect, "grant_type": "authorization_code"}).encode()
        try:
            with urllib.request.urlopen(urllib.request.Request(TOKEN_URL, data), timeout=15) as r:
                tok = json.load(r)
        except urllib.error.HTTPError:
            return self._page("Google rejected the sign-in. Check the OAuth client and redirect URI.")
        rt = tok.get("refresh_token")
        if not rt:
            return self._page("Google returned no refresh token. Remove the app at myaccount.google.com/permissions and try again.")
        self._redirect("/?" + urllib.parse.urlencode({"key": rt, "setup": "1"}),
                       "oauth_state=; Max-Age=0; Path=/api/auth")
