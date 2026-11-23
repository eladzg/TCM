"""Google Calendar sync. The clinician's Google Calendar stays the main calendar; the server mirrors it.

Read: the calendars in `gcal_read` (default: the primary one) are read when the server starts and every
15 minutes while it runs, for two weeks back and three months ahead. Each timed event becomes a row in
pm_appointments with source 'google'. Its title is kept under the identity key, because a title may
hold a patient's name; nothing else of the event is stored. An event is tied to a record by the random
record id in its private extended property `tcm_record`, which the clinician sets once from the
calendar screen.

Write: visits the system creates (a treatment series, its check-up visit) go to a separate calendar,
"קליניקה", that the server creates. Their title is neutral: the clinician's fixed word ("טיפול" by
default) or the patient's initials, never a visit type or anything clinical. The record id and the
appointment id go in private extended properties, which only this Google account sees.

Setup (docs/practice-setup.md): a Google Cloud OAuth client of type "Desktop app", its id and secret in
TCM_GOOGLE_CLIENT_ID / TCM_GOOGLE_CLIENT_SECRET, then "התחברות ליומן גוגל" in the settings screen. The
refresh token is stored encrypted under the data key.
"""
import json
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from .practice import Invalid
from .store import now

AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN = "https://oauth2.googleapis.com/token"
API = "https://www.googleapis.com/calendar/v3"
SCOPE = "https://www.googleapis.com/auth/calendar"
CLINIC_CAL = "קליניקה"


def _http(method, url, body=None, headers=None, form=None):
    data, hdrs = None, dict(headers or {})
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        hdrs["Content-Type"] = "application/x-www-form-urlencoded"
    elif body is not None:
        data = json.dumps(body).encode()
        hdrs["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        if e.code in (404, 410) and method == "DELETE":
            return {}
        raise RuntimeError(f"Google {e.code}: {e.read()[:300]!r}")


def _rfc(ts):
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(dt):
    return int(datetime.fromisoformat(dt.replace("Z", "+00:00")).timestamp())


class GoogleCalendar:
    def __init__(self, practice, settings, http=None):
        self.pm = practice
        self.s = settings
        self.http = http or _http
        self._access = (None, 0)

    # ---- configuration and sign-in ----
    @property
    def configured(self):
        return bool(self.s.google_client_id and self.s.google_client_secret)

    @property
    def connected(self):
        return self.configured and bool(self.pm.secret_get("gcal_refresh"))

    def redirect_uri(self):
        return self.s.public_base.rstrip("/") + "/api/pm/gcal/callback"

    def status(self):
        return {"configured": self.configured, "connected": self.connected,
                "read_calendars": self.pm.kv_get("gcal_read", ["primary"]),
                "clinic_calendar": self.pm.kv_get("gcal_clinic_cal"),
                "title": self.pm.kv_get("gcal_title", {"mode": "fixed", "text": "טיפול"}),
                "last_sync": self.pm.kv_get("gcal_last_sync"), "last_error": self.pm.kv_get("gcal_last_error")}

    def auth_url(self):
        if not self.configured:
            raise Invalid("set TCM_GOOGLE_CLIENT_ID and TCM_GOOGLE_CLIENT_SECRET first")
        state = secrets.token_urlsafe(16)
        self.pm.kv_set("gcal_oauth_state", {"state": state, "at": now()})
        q = {"client_id": self.s.google_client_id, "redirect_uri": self.redirect_uri(), "response_type": "code",
             "scope": SCOPE, "access_type": "offline", "prompt": "consent", "state": state}
        return AUTH + "?" + urllib.parse.urlencode(q)

    def callback(self, code, state):
        saved = self.pm.kv_get("gcal_oauth_state") or {}
        if not state or state != saved.get("state") or now() - saved.get("at", 0) > 900:
            raise Invalid("the sign-in link expired, start again")
        tok = self.http("POST", TOKEN, form={"code": code, "client_id": self.s.google_client_id, "client_secret": self.s.google_client_secret,
                                            "redirect_uri": self.redirect_uri(), "grant_type": "authorization_code"})
        if not tok.get("refresh_token"):
            raise Invalid("Google sent no refresh token")
        self.pm.secret_set("gcal_refresh", tok["refresh_token"])
        self._access = (tok.get("access_token"), time.time() + int(tok.get("expires_in", 0)) - 60)
        self.pm.kv_set("gcal_oauth_state", {})

    def disconnect(self):
        self.pm.secret_set("gcal_refresh", None)
        self._access = (None, 0)

    def set_config(self, data):
        if "read_calendars" in data:
            cals = [str(x)[:200] for x in data["read_calendars"] if str(x).strip()][:10]
            self.pm.kv_set("gcal_read", cals or ["primary"])
        if "title" in data:
            t = data["title"] or {}
            mode = t.get("mode") if t.get("mode") in ("fixed", "initials", "record") else "fixed"
            text = str(t.get("text") or "טיפול")[:40]
            from .whatsapp import check
            if mode == "fixed" and check(text):
                raise Invalid("the calendar title must not be clinical")
            self.pm.kv_set("gcal_title", {"mode": mode, "text": text})

    def token(self):
        tok, exp = self._access
        if tok and time.time() < exp:
            return tok
        refresh = self.pm.secret_get("gcal_refresh")
        if not refresh:
            raise Invalid("Google Calendar is not connected")
        res = self.http("POST", TOKEN, form={"refresh_token": refresh, "client_id": self.s.google_client_id,
                                            "client_secret": self.s.google_client_secret, "grant_type": "refresh_token"})
        self._access = (res["access_token"], time.time() + int(res.get("expires_in", 3600)) - 60)
        return self._access[0]

    def call(self, method, path, body=None, query=None):
        url = API + path + ("?" + urllib.parse.urlencode(query) if query else "")
        return self.http(method, url, body=body, headers={"Authorization": "Bearer " + self.token()})

    # ---- sync ----
    def clinic_calendar(self):
        cal = self.pm.kv_get("gcal_clinic_cal")
        if not cal:
            cal = self.call("POST", "/calendars", {"summary": CLINIC_CAL, "timeZone": str(self.pm.tz)})["id"]
            self.pm.kv_set("gcal_clinic_cal", cal)
        return cal

    def title_for(self, rid):
        t = self.pm.kv_get("gcal_title", {"mode": "fixed", "text": "טיפול"})
        if t["mode"] == "record" and rid:
            return rid
        if t["mode"] == "initials" and rid:
            with self.pm.db() as c:
                ident = self.pm.store._get_identity(c, rid) or {}
            parts = [p for p in (ident.get("name") or "").split() if p]
            if parts:
                return ".".join(p[0] for p in parts[:3]) + "."
        return t.get("text") or "טיפול"

    def sync(self):
        if not self.connected:
            return {"skipped": "not connected"}
        try:
            out = {"pulled": self.pull(), "pushed": self.push()}
            self.pm.kv_set("gcal_last_sync", self.pm.fmt(now()))
            self.pm.kv_set("gcal_last_error", None)
            return out
        except Exception as e:  # noqa: BLE001 - the error shows in the settings screen
            self.pm.kv_set("gcal_last_error", str(e)[:300])
            raise

    def _events(self, cal):
        q = {"timeMin": _rfc(now() - 14 * 86400), "timeMax": _rfc(now() + 92 * 86400), "singleEvents": "true",
             "showDeleted": "true", "maxResults": "2500"}
        items, token = [], None
        for _ in range(20):
            if token:
                q["pageToken"] = token
            res = self.call("GET", "/calendars/" + urllib.parse.quote(cal, safe="") + "/events", query=q)
            items += res.get("items") or []
            token = res.get("nextPageToken")
            if not token:
                break
        return items

    def pull(self):
        n = 0
        clinic = self.pm.kv_get("gcal_clinic_cal")
        cals = list(self.pm.kv_get("gcal_read", ["primary"]))
        if clinic and clinic not in cals:
            cals.append(clinic)
        with self.pm.db() as c:
            records = {r["record_id"] for r in c.execute("SELECT record_id FROM records")}
        for cal in cals:
            for ev in self._events(cal):
                n += self._upsert(cal, ev, records, cal == clinic)
        return n

    def _upsert(self, cal, ev, records, is_clinic):
        start = (ev.get("start") or {}).get("dateTime")
        end = (ev.get("end") or {}).get("dateTime")
        priv = (ev.get("extendedProperties") or {}).get("private") or {}
        with self.pm.db() as c:
            row = c.execute("SELECT * FROM pm_appointments WHERE gcal_cal = ? AND gcal_id = ?", (cal, ev["id"])).fetchone()
            if not row and priv.get("tcm_appt"):
                row = c.execute("SELECT * FROM pm_appointments WHERE id = ?", (priv["tcm_appt"],)).fetchone()
            if ev.get("status") == "cancelled":
                if row and row["status"] not in ("done", "no_show", "cancelled"):
                    c.execute("UPDATE pm_appointments SET status = 'cancelled', gcal_state = '', updated_at = ? WHERE id = ?", (now(), row["id"]))
                    c.execute("UPDATE pm_queue SET status = 'cancelled' WHERE appt_id = ? AND status = 'pending'", (row["id"],))
                    return 1
                return 0
            if not start or not end:
                return 0     # all-day events are not visits
            s, e = _parse(start), _parse(end)
            minutes = max(5, (e - s) // 60)
            rid = priv.get("tcm_record") if priv.get("tcm_record") in records else None
            if row:
                if row["gcal_state"] == "push":
                    return 0    # a local change waits to be written; it wins
                changed = s != row["start"] or minutes != row["minutes"]
                c.execute("UPDATE pm_appointments SET start = ?, minutes = ?, gcal_id = ?, gcal_cal = ?, record_id = COALESCE(?, record_id), updated_at = ? WHERE id = ?",
                          (s, minutes, ev["id"], cal, rid, now(), row["id"]))
                if changed:
                    c.execute("UPDATE pm_queue SET status = 'cancelled' WHERE appt_id = ? AND status = 'pending'", (row["id"],))
                aid = row["id"]
            else:
                if is_clinic:
                    return 0    # someone else's event in the clinic calendar that we did not make: leave it
                from .practice import new_id
                aid = new_id("A")
                price = c.execute("SELECT price FROM pm_prices WHERE kind = 'followup'").fetchone()
                c.execute("INSERT INTO pm_appointments (id, record_id, start, minutes, kind, status, source, gcal_id, gcal_cal, gcal_state, price, created_at, updated_at) "
                          "VALUES (?, ?, ?, ?, 'followup', 'booked', 'google', ?, ?, '', ?, ?, ?)",
                          (aid, rid, s, minutes, ev["id"], cal, price["price"] if price else None, now(), now()))
            if not is_clinic:
                kid, nonce, blob = self.pm.seal("identity", str(ev.get("summary") or "")[:200], f"appt|{aid}|title")
                c.execute("UPDATE pm_appointments SET title_kid = ?, title_nonce = ?, title_blob = ? WHERE id = ?", (kid, nonce, blob, aid))
        return 1

    def push(self):
        with self.pm.db() as c:
            rows = [dict(r) for r in c.execute("SELECT * FROM pm_appointments WHERE gcal_state IN ('push', 'delete')")]
        n = 0
        for r in rows:
            if r["gcal_state"] == "delete":
                if r["gcal_id"]:
                    self.call("DELETE", f"/calendars/{urllib.parse.quote(r['gcal_cal'], safe='')}/events/{r['gcal_id']}")
                self._done(r["id"])
                n += 1
                continue
            body = {"start": {"dateTime": _rfc(r["start"])}, "end": {"dateTime": _rfc(r["start"] + r["minutes"] * 60)},
                    "extendedProperties": {"private": {"tcm_appt": r["id"], **({"tcm_record": r["record_id"]} if r["record_id"] else {})}}}
            if r["source"] == "clinic":
                body["summary"] = self.title_for(r["record_id"])
                if r["status"] == "cancelled":
                    body["status"] = "cancelled"
                if r["gcal_id"]:
                    self.call("PATCH", f"/calendars/{urllib.parse.quote(r['gcal_cal'], safe='')}/events/{r['gcal_id']}", body)
                    self._done(r["id"])
                else:
                    cal = self.clinic_calendar()
                    ev = self.call("POST", f"/calendars/{urllib.parse.quote(cal, safe='')}/events", body)
                    self._done(r["id"], ev.get("id"), cal)
            else:
                # An event that came from the clinician's own calendar: only its time and the private link change.
                self.call("PATCH", f"/calendars/{urllib.parse.quote(r['gcal_cal'], safe='')}/events/{r['gcal_id']}", body)
                self._done(r["id"])
            n += 1
        return n

    def _done(self, aid, gcal_id=None, cal=None):
        with self.pm.db() as c:
            if gcal_id:
                c.execute("UPDATE pm_appointments SET gcal_state = 'synced', gcal_id = ?, gcal_cal = ? WHERE id = ?", (gcal_id, cal, aid))
            else:
                c.execute("UPDATE pm_appointments SET gcal_state = 'synced' WHERE id = ?", (aid,))


def week_bounds(pm, day):
    start = day - timedelta(days=(day.weekday() + 1) % 7)   # Sunday
    a, _ = pm.day_bounds(start)
    b, _ = pm.day_bounds(start + timedelta(days=7))
    return start, a, b
