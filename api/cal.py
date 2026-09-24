"""Vercel serverless Google Calendar API for the wallpaper page.

Env vars: GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN, ACCESS_KEY.
Every request must send the ACCESS_KEY in the X-Key header.
"""
import datetime as dt
import hmac
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler

API = "https://www.googleapis.com/calendar/v3"
TOKEN_URL = "https://oauth2.googleapis.com/token"
_access = {"token": None, "exp": 0}


def access_token():
    if _access["token"] and time.time() < _access["exp"] - 60:
        return _access["token"]
    data = urllib.parse.urlencode({
        "client_id": os.environ["GOOGLE_CLIENT_ID"],
        "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
        "refresh_token": os.environ["GOOGLE_REFRESH_TOKEN"],
        "grant_type": "refresh_token",
    }).encode()
    with urllib.request.urlopen(urllib.request.Request(TOKEN_URL, data), timeout=15) as r:
        tok = json.load(r)
    _access["token"] = tok["access_token"]
    _access["exp"] = time.time() + tok.get("expires_in", 3600)
    return _access["token"]


def gapi(method, path, params=None, body=None):
    url = API + path + ("?" + urllib.parse.urlencode(params) if params else "")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": "Bearer " + access_token(), "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        raw = r.read()
        return json.loads(raw) if raw else {}


def cal_events(cal, start, end):
    try:
        items = gapi("GET", f"/calendars/{urllib.parse.quote(cal['id'], safe='')}/events", {
            "timeMin": start, "timeMax": end, "singleEvents": "true",
            "orderBy": "startTime", "maxResults": 250}).get("items", [])
    except urllib.error.HTTPError:
        return []
    out = []
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


def list_events(start, end):
    cals = [c for c in gapi("GET", "/users/me/calendarList").get("items", []) if c.get("selected")]
    with ThreadPoolExecutor(max_workers=8) as ex:
        return [e for part in ex.map(lambda c: cal_events(c, start, end), cals) for e in part]


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


class handler(BaseHTTPRequestHandler):
    def _send(self, code, obj=None):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if obj is not None:
            self.wfile.write(json.dumps(obj).encode())

    def _run(self, fn):
        key = os.environ.get("ACCESS_KEY", "")
        if not key or not hmac.compare_digest(self.headers.get("X-Key", ""), key):
            return self._send(401, {"error": "unauthorized"})
        q = {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).items()}
        try:
            self._send(200, fn(q))
        except urllib.error.HTTPError as e:
            self._send(e.code, {"error": e.read().decode(errors="replace")[:300]})
        except Exception as e:  # noqa: BLE001
            self._send(500, {"error": str(e)})

    def do_GET(self):
        self._run(lambda q: list_events(q["start"], q["end"]))

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        self._run(lambda q: create_event(body))

    def do_DELETE(self):
        self._run(lambda q: gapi(
            "DELETE", f"/calendars/{urllib.parse.quote(q['cal'], safe='')}/events/{urllib.parse.quote(q['id'], safe='')}") or {"ok": True})
