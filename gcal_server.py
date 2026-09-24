"""Local Google Calendar bridge for the Lively calendar wallpaper.

Signs in once through your normal browser (OAuth loopback + PKCE), stores a
refresh token in token.json, then serves events at http://127.0.0.1:8765.
Standard library only.
"""
import base64
import datetime as dt
import hashlib
import http.server
import json
import os
import secrets
import socketserver
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
SECRET_FILE = os.path.join(HERE, "client_secret.json")
TOKEN_FILE = os.path.join(HERE, "token.json")
PORT = 8765
SCOPE = "https://www.googleapis.com/auth/calendar"
API = "https://www.googleapis.com/calendar/v3"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"

_lock = threading.Lock()
_access = {"token": None, "exp": 0}


def load_client():
    with open(SECRET_FILE, encoding="utf-8") as f:
        c = json.load(f)
    c = c.get("installed") or c.get("web")
    return c["client_id"], c["client_secret"]


def post_form(url, data):
    req = urllib.request.Request(url, urllib.parse.urlencode(data).encode())
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def login():
    """Interactive first-time sign-in via the system browser."""
    client_id, client_secret = load_client()
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(16)
    result = {}

    class CB(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if q.get("state", [""])[0] == state and "code" in q:
                result["code"] = q["code"][0]
                msg = "Signed in. You can close this tab."
            else:
                msg = "Sign-in failed: " + q.get("error", ["unknown"])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(f"<h2 style='font-family:sans-serif'>{msg}</h2>".encode())

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), CB)
    redirect = f"http://127.0.0.1:{srv.server_port}"
    url = AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": client_id, "redirect_uri": redirect, "response_type": "code",
        "scope": SCOPE, "state": state, "code_challenge": challenge,
        "code_challenge_method": "S256", "access_type": "offline", "prompt": "consent",
    })
    print("Opening browser for Google sign-in...")
    webbrowser.open(url)
    srv.timeout = 300
    srv.handle_request()
    srv.server_close()
    if "code" not in result:
        sys.exit("Sign-in did not complete.")
    tok = post_form(TOKEN_URL, {
        "client_id": client_id, "client_secret": client_secret, "code": result["code"],
        "code_verifier": verifier, "redirect_uri": redirect, "grant_type": "authorization_code",
    })
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        json.dump({"refresh_token": tok["refresh_token"]}, f)
    print("Signed in.")


def access_token():
    with _lock:
        if _access["token"] and time.time() < _access["exp"] - 60:
            return _access["token"]
        with open(TOKEN_FILE, encoding="utf-8") as f:
            refresh = json.load(f)["refresh_token"]
        client_id, client_secret = load_client()
        tok = post_form(TOKEN_URL, {
            "client_id": client_id, "client_secret": client_secret,
            "refresh_token": refresh, "grant_type": "refresh_token",
        })
        _access["token"] = tok["access_token"]
        _access["exp"] = time.time() + tok.get("expires_in", 3600)
        return _access["token"]


def gapi(method, path, params=None, body=None):
    url = API + path + ("?" + urllib.parse.urlencode(params) if params else "")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": "Bearer " + access_token(), "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        raw = r.read()
        return json.loads(raw) if raw else {}


def list_events(start, end):
    out = []
    cals = gapi("GET", "/users/me/calendarList").get("items", [])
    for cal in cals:
        if not cal.get("selected"):
            continue
        try:
            items = gapi("GET", f"/calendars/{urllib.parse.quote(cal['id'], safe='')}/events", {
                "timeMin": start, "timeMax": end, "singleEvents": "true",
                "orderBy": "startTime", "maxResults": 250}).get("items", [])
        except urllib.error.HTTPError:
            continue
        for e in items:
            if e.get("status") == "cancelled":
                continue
            s, en = e.get("start", {}), e.get("end", {})
            out.append({
                "id": e["id"], "cal": cal["id"], "color": cal.get("backgroundColor", "#6ea0ff"),
                "title": e.get("summary", "(no title)"),
                "allDay": "date" in s, "start": s.get("dateTime") or s.get("date"),
                "end": en.get("dateTime") or en.get("date"),
                "writable": cal.get("accessRole") in ("owner", "writer"),
            })
    return out


def create_event(d):
    ev = {"summary": d["title"]}
    if d.get("allDay"):
        day = dt.date.fromisoformat(d["date"])
        ev["start"] = {"date": day.isoformat()}
        ev["end"] = {"date": (day + dt.timedelta(days=1)).isoformat()}
    else:
        ev["start"] = {"dateTime": d["start"]}
        ev["end"] = {"dateTime": d["end"]}
    return gapi("POST", "/calendars/primary/events", body=ev)


_login_thread = None


def signed_in():
    return os.path.exists(TOKEN_FILE)


def start_login():
    """Run the browser sign-in in the background (triggered by the page's button)."""
    global _login_thread
    if _login_thread and _login_thread.is_alive():
        return {"started": False, "reason": "already in progress"}
    _login_thread = threading.Thread(target=login, daemon=True)
    _login_thread.start()
    return {"started": True}


class Handler(http.server.BaseHTTPRequestHandler):
    def _origin_ok(self):
        # Lively pages send "null" (file://) or a localhost origin; reject real websites.
        o = self.headers.get("Origin")
        return o is None or o == "null" or urllib.parse.urlparse(o).hostname in ("localhost", "127.0.0.1")

    def _send(self, code, obj=None):
        self.send_response(code)
        o = self.headers.get("Origin")
        if o:
            self.send_header("Access-Control-Allow-Origin", o)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        if obj is not None:
            self.wfile.write(json.dumps(obj).encode())

    def _handle(self, fn):
        if not self._origin_ok():
            return self._send(403, {"error": "forbidden origin"})
        try:
            self._send(200, fn())
        except FileNotFoundError:
            self._send(401, {"error": "not_signed_in"})
        except urllib.error.HTTPError as e:
            self._send(e.code, {"error": e.read().decode(errors="replace")[:300]})
        except Exception as e:  # noqa: BLE001
            self._send(500, {"error": str(e)})

    def do_OPTIONS(self):
        self._send(204) if self._origin_ok() else self._send(403)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        if u.path == "/status":
            return self._handle(lambda: {"ok": True, "signedIn": signed_in()})
        if u.path == "/events":
            return self._handle(lambda: list_events(q["start"], q["end"]))
        self._send(404, {"error": "not found"})

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(n) or b"{}")
        path = urllib.parse.urlparse(self.path).path
        if path == "/login":
            return self._handle(start_login)
        if path == "/events":
            return self._handle(lambda: create_event(body))
        self._send(404, {"error": "not found"})

    def do_DELETE(self):
        q = {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).items()}
        self._handle(lambda: gapi("DELETE", f"/calendars/{urllib.parse.quote(q['cal'], safe='')}/events/{q['id']}") or {"ok": True})

    def log_message(self, *a):
        pass


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


if __name__ == "__main__":
    if not os.path.exists(SECRET_FILE):
        sys.exit("Missing client_secret.json - see README.md step 1.")
    if "--login" in sys.argv:
        login()
        sys.exit(0)  # sign-in only; otherwise use the "Sign in" button on the wallpaper
    print(f"Calendar bridge running on http://127.0.0.1:{PORT}")
    Server(("127.0.0.1", PORT), Handler).serve_forever()
