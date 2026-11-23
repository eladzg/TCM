"""Practice management: appointments, treatment series, visit notes, standing alerts, MYMOP outcomes,
consent forms, prices and payments, patient form links, the "today" list, a record timeline and
clinic statistics.

Same rules as store.py: ids, times and workflow states are in the clear; every free text (note bodies,
alert wording, MYMOP symptom names, signatures, patient replies) is an AES-GCM blob under the data key,
and anything that may carry a name (a Google event title, an unknown sender's phone) is under the
identity key. Each blob's associated data names its table, row and version, so a blob copied to another
row does not open.

Times are stored as UTC epoch seconds; the API speaks the clinic's local time (settings.timezone,
"Asia/Jerusalem" by default) as "YYYY-MM-DDTHH:MM".
"""
import json
import secrets
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from . import hebcal
from .store import now, sha256

SCHEMA = """
CREATE TABLE IF NOT EXISTS pm_appointments (
  id TEXT PRIMARY KEY,
  record_id TEXT REFERENCES records(record_id) ON DELETE CASCADE,
  start INTEGER NOT NULL,
  minutes INTEGER NOT NULL,
  kind TEXT NOT NULL,
  status TEXT NOT NULL,
  series_id TEXT,
  series_no INTEGER,
  source TEXT NOT NULL DEFAULT 'clinic',
  gcal_id TEXT,
  gcal_cal TEXT,
  gcal_state TEXT NOT NULL DEFAULT '',
  title_kid TEXT, title_nonce BLOB, title_blob BLOB,
  price INTEGER,
  package_id TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS pm_appt_start ON pm_appointments(start);
CREATE UNIQUE INDEX IF NOT EXISTS pm_appt_gcal ON pm_appointments(gcal_cal, gcal_id) WHERE gcal_id IS NOT NULL;
CREATE TABLE IF NOT EXISTS pm_series (
  id TEXT PRIMARY KEY,
  record_id TEXT NOT NULL REFERENCES records(record_id) ON DELETE CASCADE,
  plan_version INTEGER,
  length INTEGER NOT NULL,
  per_week INTEGER NOT NULL,
  followup_appt TEXT,
  created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS pm_notes (
  id TEXT NOT NULL,
  version INTEGER NOT NULL,
  record_id TEXT NOT NULL REFERENCES records(record_id) ON DELETE CASCADE,
  appt_id TEXT,
  created_at INTEGER NOT NULL,
  created_by TEXT NOT NULL,
  key_id TEXT NOT NULL, nonce BLOB NOT NULL, blob BLOB NOT NULL,
  PRIMARY KEY (id, version)
);
CREATE TABLE IF NOT EXISTS pm_alerts (
  id TEXT PRIMARY KEY,
  record_id TEXT NOT NULL REFERENCES records(record_id) ON DELETE CASCADE,
  code TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1,
  version INTEGER NOT NULL DEFAULT 1,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  key_id TEXT, nonce BLOB, blob BLOB
);
CREATE TABLE IF NOT EXISTS pm_outcomes (
  id TEXT PRIMARY KEY,
  record_id TEXT NOT NULL REFERENCES records(record_id) ON DELETE CASCADE,
  appt_id TEXT,
  at INTEGER NOT NULL,
  source TEXT NOT NULL,
  s1 INTEGER, s2 INTEGER, activity INTEGER, wellbeing INTEGER,
  key_id TEXT, nonce BLOB, blob BLOB
);
CREATE TABLE IF NOT EXISTS pm_consents (
  id TEXT PRIMARY KEY,
  record_id TEXT NOT NULL REFERENCES records(record_id) ON DELETE CASCADE,
  kind TEXT NOT NULL,
  form_version TEXT NOT NULL,
  signed_at INTEGER NOT NULL,
  revoked_at INTEGER,
  source TEXT NOT NULL,
  key_id TEXT NOT NULL, nonce BLOB NOT NULL, blob BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS pm_prices (
  kind TEXT PRIMARY KEY,
  label TEXT NOT NULL,
  minutes INTEGER NOT NULL,
  price INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS pm_packages (
  id TEXT PRIMARY KEY,
  record_id TEXT NOT NULL REFERENCES records(record_id) ON DELETE CASCADE,
  label TEXT NOT NULL,
  sessions INTEGER NOT NULL,
  price INTEGER NOT NULL,
  created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS pm_payments (
  id TEXT PRIMARY KEY,
  record_id TEXT NOT NULL REFERENCES records(record_id) ON DELETE CASCADE,
  amount INTEGER NOT NULL,
  at INTEGER NOT NULL,
  method TEXT NOT NULL,
  receipt_no TEXT,
  package_id TEXT,
  appt_id TEXT
);
CREATE TABLE IF NOT EXISTS pm_tokens (
  token_hash TEXT PRIMARY KEY,
  record_id TEXT NOT NULL REFERENCES records(record_id) ON DELETE CASCADE,
  tasks TEXT NOT NULL,
  expires_at INTEGER NOT NULL,
  used_at INTEGER
);
CREATE TABLE IF NOT EXISTS pm_queue (
  id TEXT PRIMARY KEY,
  record_id TEXT REFERENCES records(record_id) ON DELETE CASCADE,
  appt_id TEXT,
  template TEXT NOT NULL,
  params TEXT NOT NULL DEFAULT '{}',
  due_at INTEGER NOT NULL,
  not_after INTEGER,
  status TEXT NOT NULL,
  tries INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  wa_message_id TEXT,
  sent_at INTEGER,
  created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS pm_messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  record_id TEXT,
  template TEXT NOT NULL,
  channel TEXT NOT NULL,
  at INTEGER NOT NULL,
  status TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS pm_inbound (
  id TEXT PRIMARY KEY,
  record_id TEXT REFERENCES records(record_id) ON DELETE CASCADE,
  at INTEGER NOT NULL,
  wa_message_id TEXT UNIQUE,
  kind TEXT NOT NULL,
  payload TEXT,
  appt_id TEXT,
  handled INTEGER NOT NULL DEFAULT 0,
  key_id TEXT, nonce BLOB, blob BLOB,
  from_kid TEXT, from_nonce BLOB, from_blob BLOB
);
CREATE TABLE IF NOT EXISTS pm_days_off (
  day TEXT PRIMARY KEY,
  label TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS pm_kv (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""

KINDS = {
    "first": ("ביקור ראשון", 90, 0),
    "followup": ("טיפול המשך", 60, 0),
    "herbs_pickup": ("איסוף צמחים", 15, 0),
    "check": ("מפגש מעקב", 45, 0),
}
APPT_STATUSES = ("booked", "confirmed", "change_requested", "done", "no_show", "cancelled")
# Standing alerts. The code is what the treatment safety check reads (the interview's category C flags);
# "PREGNANCY" sets the pregnancy status instead.
ALERT_CODES = {
    "PREGNANCY": "היריון",
    "ANTICOAGULANT": "נוגדי קרישה / נוגדי טסיות",
    "ANTIDIABETIC": "תרופות לסוכרת",
    "ANTIDEPRESSANT": "נוגדי דיכאון",
    "DIGOXIN": "דיגוקסין",
    "DEVICE": "קוצב לב או מכשיר מושתל",
    "EPILEPSY": "אפילפסיה",
    "IMMUNO": "דיכוי חיסוני או כימותרפיה",
    "ORGAN": "מחלת כבד או כליות",
    "ALLERGY": "אלרגיה",
    "NEEDLE": "רגישות למחטים / התעלפות",
    "OTHER": "אחר",
}
CONSENT_KINDS = ("treatment", "privacy", "whatsapp")
FORM_TASKS = ("consent:treatment", "consent:privacy", "consent:whatsapp", "mymop")
PAY_METHODS = ("cash", "card", "transfer", "bit", "check", "other")
NOTE_FIELDS = ("complaint", "findings", "tongue", "pulse", "done", "response", "next", "tags")


class Invalid(ValueError):
    pass


def new_id(prefix):
    return prefix + "-" + secrets.token_hex(6)


def _int(v, lo, hi, name):
    try:
        v = int(v)
    except (TypeError, ValueError):
        raise Invalid(f"{name} must be a whole number")
    if not lo <= v <= hi:
        raise Invalid(f"{name} must be between {lo} and {hi}")
    return v


def _text(v, limit=4000):
    if v is None:
        return ""
    if not isinstance(v, str):
        raise Invalid("expected text")
    return v[:limit]


class Practice:
    def __init__(self, store, tz="Asia/Jerusalem"):
        self.store = store
        self.box = store.box
        self.tz = ZoneInfo(tz)
        with store.db() as c:
            c.executescript(SCHEMA)
            if not c.execute("SELECT 1 FROM pm_prices LIMIT 1").fetchone():
                for k, (label, minutes, price) in KINDS.items():
                    c.execute("INSERT INTO pm_prices VALUES (?, ?, ?, ?)", (k, label, minutes, price))

    # ---- helpers ----
    def db(self):
        return self.store.db()

    def seal(self, name, obj, aad):
        return self.box.seal(name, obj, aad)

    def open(self, name, kid, nonce, blob, aad):
        if kid is None:
            return None
        return self.box.open(name, kid, nonce, blob, aad)

    def audit(self, c, actor, action, rid=None):
        self.store.audit(c, actor, action, rid)

    def local(self, ts):
        return datetime.fromtimestamp(ts, self.tz)

    def fmt(self, ts):
        return self.local(ts).strftime("%Y-%m-%dT%H:%M") if ts else None

    def parse(self, text):
        try:
            d = datetime.strptime(str(text)[:16], "%Y-%m-%dT%H:%M")
        except ValueError:
            raise Invalid("time must look like 2026-11-29T16:00")
        return int(d.replace(tzinfo=self.tz).timestamp())

    def day_bounds(self, day):
        start = datetime(day.year, day.month, day.day, tzinfo=self.tz)
        return int(start.timestamp()), int((start + timedelta(days=1)).timestamp())

    def today(self):
        return datetime.now(self.tz).date()

    def record_exists(self, c, rid):
        if not c.execute("SELECT 1 FROM records WHERE record_id = ?", (rid,)).fetchone():
            raise Invalid("no such record")

    # ---- key/value settings ----
    def kv_get(self, key, default=None):
        with self.db() as c:
            row = c.execute("SELECT value FROM pm_kv WHERE key = ?", (key,)).fetchone()
        return json.loads(row["value"]) if row else default

    def kv_set(self, key, value):
        with self.db() as c:
            c.execute("INSERT OR REPLACE INTO pm_kv VALUES (?, ?)", (key, json.dumps(value, ensure_ascii=False)))

    def secret_get(self, key):
        v = self.kv_get("secret:" + key)
        if not v:
            return None
        import base64
        return self.box.open("data", v["k"], base64.b64decode(v["n"]), base64.b64decode(v["b"]), "kv|" + key)

    def secret_set(self, key, value):
        import base64
        if value is None:
            with self.db() as c:
                c.execute("DELETE FROM pm_kv WHERE key = ?", ("secret:" + key,))
            return
        kid, nonce, blob = self.box.seal("data", value, "kv|" + key)
        self.kv_set("secret:" + key, {"k": kid, "n": base64.b64encode(nonce).decode(), "b": base64.b64encode(blob).decode()})

    # ---- working days ----
    def days_off(self, year=None):
        out = {}
        years = [year] if year else [self.today().year, self.today().year + 1]
        for y in years:
            out.update({d.isoformat(): n for d, n in hebcal.holidays(y).items()})
        with self.db() as c:
            for r in c.execute("SELECT day, label FROM pm_days_off"):
                out[r["day"]] = r["label"]
        return out

    def set_day_off(self, day, label, actor):
        date.fromisoformat(day)
        with self.db() as c:
            if label:
                c.execute("INSERT OR REPLACE INTO pm_days_off VALUES (?, ?)", (day, _text(label, 80)))
            else:
                c.execute("DELETE FROM pm_days_off WHERE day = ?", (day,))
            self.audit(c, actor, "day_off:" + day)

    def workdays(self):
        """Weekdays the clinic works, Python numbering (Monday = 0). Default Sunday to Thursday."""
        return self.kv_get("workdays", [6, 0, 1, 2, 3])

    def is_workday(self, d, off=None):
        off = off if off is not None else self.days_off(d.year)
        return d.weekday() in self.workdays() and d.isoformat() not in off

    def previous_workday(self, d):
        off = self.days_off(d.year)
        off.update(self.days_off(d.year - 1))
        d = d - timedelta(days=1)
        for _ in range(30):
            if self.is_workday(d, off):
                return d
            d -= timedelta(days=1)
        return d

    # ---- prices ----
    def prices(self):
        with self.db() as c:
            return [dict(r) for r in c.execute("SELECT * FROM pm_prices ORDER BY minutes DESC")]

    def set_price(self, kind, label, minutes, price, actor):
        if not kind or not kind.replace("_", "").isalnum() or len(kind) > 30:
            raise Invalid("bad kind")
        with self.db() as c:
            c.execute("INSERT OR REPLACE INTO pm_prices VALUES (?, ?, ?, ?)",
                      (kind, _text(label, 60) or kind, _int(minutes, 5, 480, "minutes"), _int(price, 0, 100000, "price")))
            self.audit(c, actor, "price:" + kind)

    def price_of(self, c, kind):
        row = c.execute("SELECT * FROM pm_prices WHERE kind = ?", (kind,)).fetchone()
        if not row:
            raise Invalid("unknown visit kind")
        return dict(row)

    # ---- appointments ----
    def _appt_row(self, c, r, names=None):
        out = {k: r[k] for k in ("id", "record_id", "minutes", "kind", "status", "series_id", "series_no", "source",
                                  "gcal_state", "price", "package_id")}
        out["start"] = self.fmt(r["start"])
        out["end"] = self.fmt(r["start"] + r["minutes"] * 60)
        out["ts"] = r["start"]
        out["external_title"] = self.open("identity", r["title_kid"], r["title_nonce"], r["title_blob"], f"appt|{r['id']}|title") if r["title_kid"] else None
        if names is not None and r["record_id"]:
            out["name"] = names.get(r["record_id"])
        return out

    def names(self, c):
        out = {}
        for r in c.execute("SELECT record_id FROM records"):
            ident = self.store._get_identity(c, r["record_id"])
            out[r["record_id"]] = (ident or {}).get("name") or ""
        return out

    def appointments(self, frm, to, record_id=None):
        with self.db() as c:
            names = self.names(c)
            q = "SELECT * FROM pm_appointments WHERE start >= ? AND start < ?"
            args = [frm, to]
            if record_id:
                q += " AND record_id = ?"
                args.append(record_id)
            return [self._appt_row(c, r, names) for r in c.execute(q + " ORDER BY start", args)]

    def record_appointments(self, rid):
        with self.db() as c:
            return [self._appt_row(c, r) for r in c.execute("SELECT * FROM pm_appointments WHERE record_id = ? ORDER BY start", (rid,))]

    def get_appt(self, aid):
        with self.db() as c:
            r = c.execute("SELECT * FROM pm_appointments WHERE id = ?", (aid,)).fetchone()
            return self._appt_row(c, r) if r else None

    def _insert_appt(self, c, rid, start, minutes, kind, series_id=None, series_no=None, package_id=None, push=True):
        aid = new_id("A")
        price = None if package_id else self.price_of(c, kind)["price"]
        c.execute("INSERT INTO pm_appointments (id, record_id, start, minutes, kind, status, series_id, series_no, source, "
                  "gcal_state, price, package_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, 'booked', ?, ?, 'clinic', ?, ?, ?, ?, ?)",
                  (aid, rid, start, minutes, kind, series_id, series_no, "push" if push else "", price, package_id, now(), now()))
        return aid

    def add_appointment(self, actor, rid, start, kind, minutes=None, package_id=None):
        with self.db() as c:
            if rid:
                self.record_exists(c, rid)
            p = self.price_of(c, kind)
            minutes = _int(minutes or p["minutes"], 5, 480, "minutes")
            aid = self._insert_appt(c, rid, self.parse(start), minutes, kind, package_id=package_id)
            self.audit(c, actor, "appt_add:" + aid, rid)
        return aid

    def update_appointment(self, actor, aid, data):
        with self.db() as c:
            r = c.execute("SELECT * FROM pm_appointments WHERE id = ?", (aid,)).fetchone()
            if not r:
                raise Invalid("no such appointment")
            sets, args = [], []
            if "status" in data:
                if data["status"] not in APPT_STATUSES:
                    raise Invalid("unknown status")
                sets.append("status = ?"); args.append(data["status"])
            if "start" in data:
                sets.append("start = ?"); args.append(self.parse(data["start"]))
            if "minutes" in data:
                sets.append("minutes = ?"); args.append(_int(data["minutes"], 5, 480, "minutes"))
            if "record_id" in data:
                if data["record_id"]:
                    self.record_exists(c, data["record_id"])
                sets.append("record_id = ?"); args.append(data["record_id"] or None)
            if "kind" in data:
                self.price_of(c, data["kind"])
                sets.append("kind = ?"); args.append(data["kind"])
            if not sets:
                return
            if r["gcal_id"] or r["source"] == "clinic":
                sets.append("gcal_state = ?"); args.append("delete" if data.get("status") == "cancelled" and r["source"] == "clinic" else "push")
            sets.append("updated_at = ?"); args.append(now())
            c.execute("UPDATE pm_appointments SET " + ", ".join(sets) + " WHERE id = ?", args + [aid])
            if data.get("status") == "cancelled" or "start" in data:
                c.execute("UPDATE pm_queue SET status = 'cancelled' WHERE appt_id = ? AND status = 'pending'", (aid,))
            self.audit(c, actor, "appt_update:" + aid, r["record_id"])

    # ---- treatment series ----
    def plan_series(self, start_day, time, length, per_week, followup_days=14):
        """The dates of a series: every 7 days (per_week 1) or alternating 3 and 4 days (per_week 2),
        a day that is not a working day moves to the next working day. Then a check-up visit."""
        length = _int(length, 1, 40, "length")
        per_week = _int(per_week, 1, 3, "per_week")
        try:
            d = date.fromisoformat(str(start_day))
            datetime.strptime(time, "%H:%M")
        except (ValueError, TypeError):
            raise Invalid("start must be YYYY-MM-DD and time HH:MM")
        off = {}
        for y in (d.year, d.year + 1):
            off.update(self.days_off(y))
        gaps = {1: [7], 2: [3, 4], 3: [2, 2, 3]}[per_week]
        out, moved, k = [], [], 0
        while len(out) < length:
            planned = d
            while not self.is_workday(d, off):
                d += timedelta(days=1)
            if d != planned:
                moved.append({"from": planned.isoformat(), "to": d.isoformat(), "why": off.get(planned.isoformat(), "לא יום עבודה")})
            out.append(d)
            d = planned + timedelta(days=gaps[k % len(gaps)])
            if d <= out[-1]:
                d = out[-1] + timedelta(days=1)
            k += 1
        fu = out[-1] + timedelta(days=followup_days)
        while not self.is_workday(fu, off):
            fu += timedelta(days=1)
        return {"sessions": [x.isoformat() + "T" + time for x in out], "followup": fu.isoformat() + "T" + time, "moved": moved}

    def create_series(self, actor, rid, start_day, time, length, per_week, minutes=None, kind="followup",
                      first_kind=None, plan_version=None, package_id=None):
        p = self.plan_series(start_day, time, length, per_week)
        sid = new_id("S")
        with self.db() as c:
            self.record_exists(c, rid)
            ids = []
            for i, when in enumerate(p["sessions"]):
                k = first_kind if (i == 0 and first_kind) else kind
                m = _int(minutes or self.price_of(c, k)["minutes"], 5, 480, "minutes")
                ids.append(self._insert_appt(c, rid, self.parse(when), m, k, sid, i + 1, package_id))
            fu = self._insert_appt(c, rid, self.parse(p["followup"]), self.price_of(c, "check")["minutes"], "check", sid, 0)
            c.execute("INSERT INTO pm_series VALUES (?, ?, ?, ?, ?, ?, ?)", (sid, rid, plan_version, len(ids), per_week, fu, now()))
            self.audit(c, actor, "series_add:" + sid, rid)
        return {"series_id": sid, "appointments": ids, "followup": fu, "moved": p["moved"]}

    def series(self, rid):
        with self.db() as c:
            out = []
            for s in c.execute("SELECT * FROM pm_series WHERE record_id = ? ORDER BY created_at", (rid,)):
                rows = c.execute("SELECT status, series_no FROM pm_appointments WHERE series_id = ?", (s["id"],)).fetchall()
                done = sum(1 for r in rows if r["series_no"] and r["status"] == "done")
                out.append(dict(s) | {"done": done})
            return out

    # ---- visit notes ----
    def save_note(self, actor, rid, data, note_id=None):
        doc = {k: _text(data.get(k), 8000) for k in NOTE_FIELDS if data.get(k)}
        if not doc:
            raise Invalid("an empty note")
        with self.db() as c:
            self.record_exists(c, rid)
            if note_id:
                row = c.execute("SELECT MAX(version) AS v, record_id, appt_id FROM pm_notes WHERE id = ?", (note_id,)).fetchone()
                if not row or row["v"] is None or row["record_id"] != rid:
                    raise Invalid("no such note")
                v, appt = row["v"] + 1, row["appt_id"]
            else:
                note_id, v, appt = new_id("N"), 1, data.get("appt_id") or None
            kid, nonce, blob = self.seal("data", doc, f"note|{note_id}|{v}")
            c.execute("INSERT INTO pm_notes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (note_id, v, rid, appt, now(), actor, kid, nonce, blob))
            self.audit(c, actor, f"note:{note_id}:v{v}", rid)
        return note_id, v

    def notes(self, rid, history=False):
        with self.db() as c:
            rows = c.execute("SELECT * FROM pm_notes WHERE record_id = ? ORDER BY id, version", (rid,)).fetchall()
        by = {}
        for r in rows:
            item = {"id": r["id"], "version": r["version"], "appt_id": r["appt_id"], "created_at": r["created_at"],
                    "created_by": r["created_by"], "data": self.open("data", r["key_id"], r["nonce"], r["blob"], f"note|{r['id']}|{r['version']}")}
            by.setdefault(r["id"], []).append(item)
        out = []
        for nid, versions in by.items():
            last = dict(versions[-1])
            last["first_at"] = versions[0]["created_at"]
            last["versions"] = len(versions)
            if history:
                last["history"] = versions
            out.append(last)
        return sorted(out, key=lambda x: x["first_at"], reverse=True)

    # ---- standing alerts ----
    def save_alert(self, actor, rid, code, text="", active=True, alert_id=None):
        if code not in ALERT_CODES:
            raise Invalid("unknown alert code")
        with self.db() as c:
            self.record_exists(c, rid)
            if alert_id:
                r = c.execute("SELECT version FROM pm_alerts WHERE id = ? AND record_id = ?", (alert_id, rid)).fetchone()
                if not r:
                    raise Invalid("no such alert")
                v = r["version"] + 1
            else:
                alert_id, v = new_id("L"), 1
            kid, nonce, blob = self.seal("data", {"text": _text(text, 500)}, f"alert|{alert_id}|{v}")
            c.execute("INSERT OR REPLACE INTO pm_alerts VALUES (?, ?, ?, ?, ?, COALESCE((SELECT created_at FROM pm_alerts WHERE id = ?), ?), ?, ?, ?, ?)",
                      (alert_id, rid, code, 1 if active else 0, v, alert_id, now(), now(), kid, nonce, blob))
            self.audit(c, actor, f"alert:{alert_id}:{'on' if active else 'off'}", rid)
        return alert_id

    def alerts(self, rid, only_active=False):
        with self.db() as c:
            rows = c.execute("SELECT * FROM pm_alerts WHERE record_id = ?" + (" AND active = 1" if only_active else "") + " ORDER BY created_at", (rid,)).fetchall()
        return [{"id": r["id"], "code": r["code"], "label": ALERT_CODES[r["code"]], "active": bool(r["active"]),
                 "updated_at": r["updated_at"],
                 "text": (self.open("data", r["key_id"], r["nonce"], r["blob"], f"alert|{r['id']}|{r['version']}") or {}).get("text", "")}
                for r in rows]

    def alert_codes(self, c, rid):
        return [r["code"] for r in c.execute("SELECT code FROM pm_alerts WHERE record_id = ? AND active = 1", (rid,))]

    # ---- MYMOP ----
    def save_outcome(self, actor, rid, data, source="clinician"):
        scores = {k: _int(data.get(k), 0, 6, k) if data.get(k) is not None else None for k in ("s1", "s2", "activity", "wellbeing")}
        if scores["s1"] is None or scores["wellbeing"] is None:
            raise Invalid("symptom 1 and wellbeing are required")
        labels = {k: _text(data.get(k), 120) for k in ("symptom1", "symptom2", "activity_name") if data.get(k)}
        oid = new_id("O")
        with self.db() as c:
            self.record_exists(c, rid)
            if not labels:
                prev = c.execute("SELECT * FROM pm_outcomes WHERE record_id = ? AND key_id IS NOT NULL ORDER BY at DESC LIMIT 1", (rid,)).fetchone()
                if prev:
                    labels = self.open("data", prev["key_id"], prev["nonce"], prev["blob"], f"outcome|{prev['id']}") or {}
            kid, nonce, blob = self.seal("data", labels, f"outcome|{oid}") if labels else (None, None, None)
            c.execute("INSERT INTO pm_outcomes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                      (oid, rid, data.get("appt_id"), now(), source, scores["s1"], scores["s2"], scores["activity"], scores["wellbeing"], kid, nonce, blob))
            self.audit(c, actor, "mymop:" + oid, rid)
        return oid

    def outcomes(self, rid):
        with self.db() as c:
            rows = c.execute("SELECT * FROM pm_outcomes WHERE record_id = ? ORDER BY at", (rid,)).fetchall()
        return [{"id": r["id"], "at": r["at"], "appt_id": r["appt_id"], "source": r["source"],
                 "s1": r["s1"], "s2": r["s2"], "activity": r["activity"], "wellbeing": r["wellbeing"],
                 "labels": self.open("data", r["key_id"], r["nonce"], r["blob"], f"outcome|{r['id']}") or {}} for r in rows]

    # ---- consent ----
    def sign_consent(self, actor, rid, kind, form_version, signer, signature, source="clinic"):
        if kind not in CONSENT_KINDS:
            raise Invalid("unknown consent")
        if not isinstance(signature, str) or not signature.startswith("data:image/png;base64,") or len(signature) > 400_000:
            raise Invalid("signature must be a PNG data URL")
        cid = new_id("C")
        with self.db() as c:
            self.record_exists(c, rid)
            kid, nonce, blob = self.seal("data", {"signer": _text(signer, 120), "signature": signature}, f"consent|{cid}")
            c.execute("INSERT INTO pm_consents VALUES (?, ?, ?, ?, ?, NULL, ?, ?, ?, ?)",
                      (cid, rid, kind, _text(form_version, 40), now(), source, kid, nonce, blob))
            self.audit(c, actor, f"consent:{kind}:{cid}", rid)
        return cid

    def revoke_consent(self, actor, cid):
        with self.db() as c:
            r = c.execute("SELECT record_id, kind FROM pm_consents WHERE id = ?", (cid,)).fetchone()
            if not r:
                raise Invalid("no such consent")
            c.execute("UPDATE pm_consents SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL", (now(), cid))
            if r["kind"] == "whatsapp":
                c.execute("UPDATE pm_queue SET status = 'skipped_no_consent' WHERE record_id = ? AND status = 'pending'", (r["record_id"],))
            self.audit(c, actor, "consent_revoke:" + cid, r["record_id"])

    def consents(self, rid, with_signature=False):
        with self.db() as c:
            rows = c.execute("SELECT * FROM pm_consents WHERE record_id = ? ORDER BY signed_at", (rid,)).fetchall()
        out = []
        for r in rows:
            item = {k: r[k] for k in ("id", "kind", "form_version", "signed_at", "revoked_at", "source")}
            doc = self.open("data", r["key_id"], r["nonce"], r["blob"], f"consent|{r['id']}")
            item["signer"] = doc.get("signer")
            if with_signature:
                item["signature"] = doc.get("signature")
            out.append(item)
        return out

    def has_consent(self, c, rid, kind):
        return bool(c.execute("SELECT 1 FROM pm_consents WHERE record_id = ? AND kind = ? AND revoked_at IS NULL", (rid, kind)).fetchone())

    # ---- patient form links (consent and MYMOP on the patient's phone) ----
    def form_link(self, actor, rid, tasks, days=7):
        tasks = [t for t in tasks if t in FORM_TASKS]
        if not tasks:
            raise Invalid("choose at least one form")
        token = secrets.token_urlsafe(24)
        with self.db() as c:
            self.record_exists(c, rid)
            c.execute("INSERT INTO pm_tokens VALUES (?, ?, ?, ?, NULL)", (sha256(token), rid, json.dumps(tasks), now() + days * 86400))
            self.audit(c, actor, "form_link:" + ",".join(tasks), rid)
        return token, now() + days * 86400

    def form_for_token(self, token):
        with self.db() as c:
            r = c.execute("SELECT * FROM pm_tokens WHERE token_hash = ?", (sha256(token),)).fetchone()
            if not r or r["used_at"] or r["expires_at"] < now():
                return None
            out = {"record_id": r["record_id"], "tasks": json.loads(r["tasks"]), "expires_at": r["expires_at"]}
            if "mymop" in out["tasks"]:
                prev = c.execute("SELECT * FROM pm_outcomes WHERE record_id = ? AND key_id IS NOT NULL ORDER BY at DESC LIMIT 1", (r["record_id"],)).fetchone()
                labels = self.open("data", prev["key_id"], prev["nonce"], prev["blob"], f"outcome|{prev['id']}") if prev else {}
                # The patient's own symptom names come back to the patient so the follow-up form keeps them.
                out["mymop_labels"] = labels or {}
            return out

    def submit_forms(self, token, data, forms):
        info = self.form_for_token(token)
        if not info:
            return None
        rid = info["record_id"]
        for task in info["tasks"]:
            if task.startswith("consent:"):
                kind = task.split(":", 1)[1]
                got = (data.get("consents") or {}).get(kind)
                if not got:
                    continue
                if not got.get("agree"):
                    continue
                self.sign_consent("patient", rid, kind, forms[kind]["version"], got.get("signer"), got.get("signature"), source="patient_link")
            elif task == "mymop" and data.get("mymop"):
                self.save_outcome("patient", rid, data["mymop"], source="patient")
        with self.db() as c:
            c.execute("UPDATE pm_tokens SET used_at = ? WHERE token_hash = ?", (now(), sha256(token)))
            self.audit(c, "patient", "forms_submitted", rid)
        return rid

    # ---- packages and payments ----
    def add_package(self, actor, rid, label, sessions, price):
        pid = new_id("P")
        with self.db() as c:
            self.record_exists(c, rid)
            c.execute("INSERT INTO pm_packages VALUES (?, ?, ?, ?, ?, ?)",
                      (pid, rid, _text(label, 80) or "חבילה", _int(sessions, 1, 100, "sessions"), _int(price, 0, 1000000, "price"), now()))
            self.audit(c, actor, "package:" + pid, rid)
        return pid

    def add_payment(self, actor, rid, amount, method, receipt_no="", package_id=None, appt_id=None, day=None):
        if method not in PAY_METHODS:
            raise Invalid("unknown payment method")
        pid = new_id("Y")
        at = self.parse(day + "T12:00") if day else now()
        with self.db() as c:
            self.record_exists(c, rid)
            c.execute("INSERT INTO pm_payments VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                      (pid, rid, _int(amount, -1000000, 1000000, "amount"), at, method, _text(receipt_no, 40) or None, package_id, appt_id))
            self.audit(c, actor, "payment:" + pid, rid)
        return pid

    def account(self, rid):
        """What was charged (visits held or missed without a package, and packages) and what was paid."""
        with self.db() as c:
            visits = [dict(r) for r in c.execute(
                "SELECT id, start, kind, status, price, package_id FROM pm_appointments WHERE record_id = ? AND status IN ('done', 'no_show') ORDER BY start", (rid,))]
            packages = [dict(r) for r in c.execute("SELECT * FROM pm_packages WHERE record_id = ? ORDER BY created_at", (rid,))]
            payments = [dict(r) for r in c.execute("SELECT * FROM pm_payments WHERE record_id = ? ORDER BY at", (rid,))]
            for p in packages:
                p["used"] = c.execute("SELECT COUNT(*) FROM pm_appointments WHERE package_id = ? AND status IN ('done', 'no_show')", (p["id"],)).fetchone()[0]
        charged = sum(v["price"] or 0 for v in visits if not v["package_id"]) + sum(p["price"] for p in packages)
        paid = sum(p["amount"] for p in payments)
        for v in visits:
            v["start"] = self.fmt(v["start"])
        for p in payments:
            p["day"] = self.local(p["at"]).date().isoformat()
        return {"visits": visits, "packages": packages, "payments": payments, "charged": charged, "paid": paid, "balance": charged - paid}

    # ---- the "today" list ----
    def today_view(self, day=None):
        day = day or self.today()
        frm, to = self.day_bounds(day)
        with self.db() as c:
            names = self.names(c)
            appts = []
            for r in c.execute("SELECT * FROM pm_appointments WHERE start >= ? AND start < ? AND status != 'cancelled' ORDER BY start", (frm, to)):
                a = self._appt_row(c, r, names)
                if r["record_id"]:
                    a["alerts"] = self.alert_codes(c, r["record_id"])
                    a["consent_missing"] = [k for k in ("treatment", "privacy") if not self.has_consent(c, r["record_id"], k)]
                appts.append(a)
            submitted = [{"record_id": r["record_id"], "name": names.get(r["record_id"]), "at": r["updated_at"]}
                         for r in c.execute("SELECT record_id, updated_at FROM records WHERE status = 'submitted' ORDER BY updated_at")]
            in_review = [{"record_id": r["record_id"], "name": names.get(r["record_id"])}
                         for r in c.execute("SELECT record_id FROM records WHERE status = 'in_review' ORDER BY updated_at DESC LIMIT 20")]
            ended = []
            for s in c.execute("SELECT * FROM pm_series"):
                last = c.execute("SELECT MAX(start) FROM pm_appointments WHERE series_id = ? AND series_no > 0", (s["id"],)).fetchone()[0]
                fu = c.execute("SELECT status FROM pm_appointments WHERE id = ?", (s["followup_appt"],)).fetchone()
                if last and last < now() and (not fu or fu["status"] == "cancelled"):
                    later = c.execute("SELECT 1 FROM pm_appointments WHERE record_id = ? AND start > ? AND status != 'cancelled'", (s["record_id"], now())).fetchone()
                    if not later:
                        ended.append({"record_id": s["record_id"], "name": names.get(s["record_id"]), "series_id": s["id"]})
            unsent = [dict(r) | {"name": names.get(r["record_id"]), "due": self.fmt(r["due_at"])} for r in c.execute(
                "SELECT id, record_id, appt_id, template, due_at, status, last_error FROM pm_queue WHERE status IN ('failed', 'missed') "
                "OR (status = 'pending' AND due_at < ?) ORDER BY due_at", (now() - 3600,))]
            replies = [{"id": r["id"], "record_id": r["record_id"], "name": names.get(r["record_id"]), "at": r["at"], "kind": r["kind"],
                        "payload": r["payload"], "appt_id": r["appt_id"]}
                       for r in c.execute("SELECT * FROM pm_inbound WHERE handled = 0 ORDER BY at")]
            no_show = [{"record_id": r["record_id"], "name": names.get(r["record_id"]), "n": r["n"]} for r in c.execute(
                "SELECT record_id, COUNT(*) AS n FROM pm_appointments WHERE status = 'no_show' AND record_id IS NOT NULL GROUP BY record_id HAVING n >= 2")]
            unlinked = c.execute("SELECT COUNT(*) FROM pm_appointments WHERE record_id IS NULL AND start >= ? AND status != 'cancelled'", (frm,)).fetchone()[0]
            first_soon = []
            for r in c.execute("SELECT * FROM pm_appointments WHERE kind = 'first' AND status IN ('booked', 'confirmed') AND start BETWEEN ? AND ? AND record_id IS NOT NULL",
                               (now(), now() + 3 * 86400)):
                rec = c.execute("SELECT status FROM records WHERE record_id = ?", (r["record_id"],)).fetchone()
                if rec and rec["status"] == "awaiting_patient":
                    first_soon.append({"record_id": r["record_id"], "name": names.get(r["record_id"]), "start": self.fmt(r["start"])})
        return {"day": day.isoformat(), "day_off": self.days_off(day.year).get(day.isoformat()), "appointments": appts,
                "intakes_waiting": submitted, "in_review": in_review, "series_ended": ended, "unsent_messages": unsent,
                "replies": replies, "repeat_no_show": no_show, "unlinked_events": unlinked, "intake_before_first": first_soon}

    def handle_reply(self, actor, iid):
        with self.db() as c:
            r = c.execute("SELECT record_id FROM pm_inbound WHERE id = ?", (iid,)).fetchone()
            if not r:
                raise Invalid("no such reply")
            c.execute("UPDATE pm_inbound SET handled = 1 WHERE id = ?", (iid,))
            self.audit(c, actor, "reply_handled:" + iid, r["record_id"])

    def replies(self, rid):
        with self.db() as c:
            rows = c.execute("SELECT * FROM pm_inbound WHERE record_id = ? ORDER BY at", (rid,)).fetchall()
        return [{"id": r["id"], "at": r["at"], "kind": r["kind"], "payload": r["payload"], "handled": bool(r["handled"]),
                 "text": (self.open("data", r["key_id"], r["nonce"], r["blob"], f"inbound|{r['id']}") or {}).get("text")} for r in rows]

    # ---- the record timeline ----
    def timeline(self, rid):
        items = []
        with self.db() as c:
            self.record_exists(c, rid)
            rec = c.execute("SELECT created_at FROM records WHERE record_id = ?", (rid,)).fetchone()
            items.append({"at": rec["created_at"], "type": "record", "label": "התיק נפתח"})
            for r in c.execute("SELECT kind, version, created_at, created_by FROM documents WHERE record_id = ?", (rid,)):
                items.append({"at": r["created_at"], "type": "doc:" + r["kind"], "version": r["version"], "by": r["created_by"]})
            for r in c.execute("SELECT id, start, kind, status, series_no FROM pm_appointments WHERE record_id = ?", (rid,)):
                items.append({"at": r["start"], "type": "appointment", "id": r["id"], "kind": r["kind"], "status": r["status"], "series_no": r["series_no"]})
            for r in c.execute("SELECT id, MIN(created_at) AS at, MAX(version) AS v FROM pm_notes WHERE record_id = ? GROUP BY id", (rid,)):
                items.append({"at": r["at"], "type": "note", "id": r["id"], "versions": r["v"]})
            for r in c.execute("SELECT id, at, s1, s2, wellbeing, source FROM pm_outcomes WHERE record_id = ?", (rid,)):
                items.append({"at": r["at"], "type": "mymop", "s1": r["s1"], "s2": r["s2"], "wellbeing": r["wellbeing"], "source": r["source"]})
            for r in c.execute("SELECT kind, signed_at, revoked_at FROM pm_consents WHERE record_id = ?", (rid,)):
                items.append({"at": r["signed_at"], "type": "consent", "kind": r["kind"]})
                if r["revoked_at"]:
                    items.append({"at": r["revoked_at"], "type": "consent_revoked", "kind": r["kind"]})
            for r in c.execute("SELECT template, channel, at, status FROM pm_messages WHERE record_id = ?", (rid,)):
                items.append({"at": r["at"], "type": "message", "template": r["template"], "channel": r["channel"], "status": r["status"]})
            for r in c.execute("SELECT at, kind, payload FROM pm_inbound WHERE record_id = ?", (rid,)):
                items.append({"at": r["at"], "type": "reply", "kind": r["kind"], "payload": r["payload"]})
            for r in c.execute("SELECT at, amount, method FROM pm_payments WHERE record_id = ?", (rid,)):
                items.append({"at": r["at"], "type": "payment", "amount": r["amount"], "method": r["method"]})
            for r in c.execute("SELECT created_at, label, sessions FROM pm_packages WHERE record_id = ?", (rid,)):
                items.append({"at": r["created_at"], "type": "package", "label": r["label"], "sessions": r["sessions"]})
        for it in items:
            it["when"] = self.fmt(it["at"])
        return sorted(items, key=lambda x: x["at"], reverse=True)

    # ---- statistics (counts only) ----
    def stats(self, months=12):
        today = self.today()
        keys = []
        y, m = today.year, today.month
        for _ in range(months):
            keys.append(f"{y:04d}-{m:02d}")
            m -= 1
            if m == 0:
                y, m = y - 1, 12
        keys.reverse()
        per = {k: {"month": k, "visits": 0, "no_show": 0, "cancelled": 0, "new_records": 0, "revenue": 0, "messages": 0} for k in keys}

        def month(ts):
            return self.local(ts).strftime("%Y-%m")
        with self.db() as c:
            for r in c.execute("SELECT start, status FROM pm_appointments WHERE record_id IS NOT NULL"):
                k = month(r["start"])
                if k in per:
                    if r["status"] == "done":
                        per[k]["visits"] += 1
                    elif r["status"] == "no_show":
                        per[k]["no_show"] += 1
                    elif r["status"] == "cancelled":
                        per[k]["cancelled"] += 1
            for r in c.execute("SELECT created_at FROM records"):
                k = month(r["created_at"])
                if k in per:
                    per[k]["new_records"] += 1
            for r in c.execute("SELECT at, amount FROM pm_payments"):
                k = month(r["at"])
                if k in per:
                    per[k]["revenue"] += r["amount"]
            for r in c.execute("SELECT at FROM pm_messages WHERE status = 'sent'"):
                k = month(r["at"])
                if k in per:
                    per[k]["messages"] += 1
            changes = []
            for r in c.execute("SELECT record_id FROM pm_outcomes GROUP BY record_id HAVING COUNT(*) >= 2"):
                rows = c.execute("SELECT s1 FROM pm_outcomes WHERE record_id = ? ORDER BY at", (r["record_id"],)).fetchall()
                changes.append(rows[0]["s1"] - rows[-1]["s1"])
            series = c.execute("SELECT COUNT(*) FROM pm_series").fetchone()[0]
            completed = 0
            for s in c.execute("SELECT id, length FROM pm_series"):
                done = c.execute("SELECT COUNT(*) FROM pm_appointments WHERE series_id = ? AND series_no > 0 AND status = 'done'", (s["id"],)).fetchone()[0]
                completed += done >= s["length"]
        held = sum(p["visits"] for p in per.values())
        missed = sum(p["no_show"] for p in per.values())
        return {"months": list(per.values()),
                "no_show_rate": round(missed / (held + missed), 3) if held + missed else None,
                "mymop": {"patients": len(changes), "mean_change_s1": round(sum(changes) / len(changes), 2) if changes else None,
                          "improved_1_or_more": sum(1 for x in changes if x >= 1)},
                "series": {"total": series, "completed": completed}}
