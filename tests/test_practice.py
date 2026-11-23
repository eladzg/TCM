"""Practice management: calendar and holidays, series, notes and alerts, MYMOP, consent, payments,
the WhatsApp check, queue and webhook, Google Calendar sync (with a fake Google), backups."""
import hashlib
import hmac
import json
import sqlite3
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("cryptography")
from fastapi.testclient import TestClient  # noqa: E402

from server import backup, hebcal, whatsapp  # noqa: E402
from server.app import create_app  # noqa: E402
from server.auth import hash_password  # noqa: E402
from server.config import load_settings  # noqa: E402
from server.crypto import create_keys  # noqa: E402

H = {"X-TCM": "1"}
PW = "correct horse battery"
TZ = ZoneInfo("Asia/Jerusalem")
PNG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="


def build(tmp_path, **over):
    s = load_settings(data_dir=tmp_path, key_dir=tmp_path / "keys", run_jobs=False, **over)
    create_keys(s.key_dir)
    app = create_app(s)
    app.state.store.add_clinician("dana", hash_password(PW))
    c = TestClient(app)
    assert c.post("/api/login", json={"username": "dana", "password": PW}, headers=H).status_code == 200
    return app, s, c


@pytest.fixture()
def env(tmp_path):
    return build(tmp_path)


def record(c, name="דנה כהן", phone="050-1234567"):
    return c.post("/api/records", json={"identity": {"name": name, "phone": phone}}, headers=H).json()["record_id"]


def next_weekday(wd):
    d = date.today() + timedelta(days=1)
    while d.weekday() != wd:
        d += timedelta(days=1)
    return d


# ---- the Hebrew calendar ----
def test_holidays_known_dates():
    h = hebcal.holidays(2026)
    assert h[date(2026, 4, 2)] == "פסח"
    assert h[date(2026, 9, 12)] == "ראש השנה" and h[date(2026, 9, 21)] == "יום כיפור"
    h27 = hebcal.holidays(2027)
    assert h27[date(2027, 4, 22)] == "פסח" and h27[date(2027, 6, 11)] == "שבועות"
    assert date(2028, 5, 2) in hebcal.holidays(2028)   # Yom HaAtzmaut 2028 moved from Monday to Tuesday


def test_series_skips_weekend_and_holidays(env):
    app, _, c = env
    # Starting on Wednesday 2027-04-21, weekly: the 28th is the seventh day of Pesach, moved to the 29th.
    p = c.get("/api/pm/series/preview", params={"start": "2027-04-21", "time": "16:00", "length": 3, "per_week": 1}).json()
    assert p["sessions"] == ["2027-04-21T16:00", "2027-04-29T16:00", "2027-05-05T16:00"]
    assert p["moved"][0]["why"] == "שביעי של פסח"
    assert p["followup"] == "2027-05-19T16:00"
    # Twice a week from a Friday: Friday is not a working day, so the first visit is on Sunday.
    p2 = app.state.practice.plan_series("2026-11-27", "10:00", 4, 2)
    days = [datetime.fromisoformat(x).weekday() for x in p2["sessions"]]
    assert all(d in (6, 0, 1, 2, 3) for d in days) and p2["sessions"][0].startswith("2026-11-29")


def test_series_creates_appointments_and_reminders(env):
    app, _, c = env
    rid = record(c)
    start = next_weekday(6)    # a Sunday
    out = c.post(f"/api/pm/records/{rid}/series", json={"start": start.isoformat(), "time": "16:00", "length": 7, "per_week": 1, "first_kind": "first"}, headers=H).json()
    assert len(out["appointments"]) == 7
    card = c.get(f"/api/pm/records/{rid}").json()
    assert len(card["appointments"]) == 8 and card["appointments"][0]["kind"] == "first"
    # The Sunday visit's reminder is due on the Thursday before, at 10:00.
    q = [x for x in card["queue"] if x["appt_id"] == out["appointments"][0]]
    assert q and q[0]["due"] == (start - timedelta(days=3)).isoformat() + "T10:00"


# ---- notes and alerts ----
def test_notes_are_versioned_and_encrypted(env):
    app, s, c = env
    rid = record(c)
    r = c.post(f"/api/pm/records/{rid}/notes", json={"note": {"complaint": "כאב ראש סודי", "tongue": "אדומה"}}, headers=H).json()
    r2 = c.post(f"/api/pm/records/{rid}/notes", json={"note_id": r["note_id"], "note": {"complaint": "כאב ראש סודי, תיקון"}}, headers=H).json()
    assert r2["version"] == 2
    notes = c.get(f"/api/pm/records/{rid}").json()["notes"]
    assert len(notes) == 1 and notes[0]["data"]["complaint"].endswith("תיקון") and notes[0]["versions"] == 2
    hist = c.get(f"/api/pm/records/{rid}/notes/{r['note_id']}").json()["history"]
    assert hist[0]["data"]["complaint"] == "כאב ראש סודי"
    raw = (s.db_path).read_bytes() + (s.data_dir / "records.db-wal").read_bytes() if (s.data_dir / "records.db-wal").exists() else s.db_path.read_bytes()
    assert "סודי".encode() not in raw
    # the de-identified export carries no note text
    assert "סודי" not in json.dumps(c.get("/api/export").json(), ensure_ascii=False)


def test_alerts_feed_safety_codes(env):
    _, _, c = env
    rid = record(c)
    c.post(f"/api/pm/records/{rid}/alerts", json={"code": "ANTICOAGULANT", "text": "קומדין 5 מ\"ג"}, headers=H)
    a = c.post(f"/api/pm/records/{rid}/alerts", json={"code": "PREGNANCY"}, headers=H).json()
    c.post(f"/api/pm/records/{rid}/alerts", json={"code": "PREGNANCY", "alert_id": a["alert_id"], "active": False}, headers=H)
    active = c.get(f"/api/pm/records/{rid}/alerts").json()["alerts"]
    assert [x["code"] for x in active] == ["ANTICOAGULANT"] and "קומדין" in active[0]["text"]
    assert c.post(f"/api/pm/records/{rid}/alerts", json={"code": "NOPE"}, headers=H).status_code == 422


# ---- MYMOP and consent through the patient link ----
def test_patient_forms_link(env):
    app, _, c = env
    rid = record(c)
    link = c.post(f"/api/pm/records/{rid}/form-link", json={"tasks": ["consent:treatment", "consent:whatsapp", "mymop"]}, headers=H).json()
    p = TestClient(app)
    auth = {"Authorization": "Bearer " + link["token"]}
    got = p.get("/api/forms", headers=auth).json()
    assert set(got["forms"]) == {"treatment", "whatsapp"} and got["mymop"]
    body = {"consents": {"treatment": {"agree": True, "signer": "דנה", "signature": PNG}, "whatsapp": {"agree": True, "signer": "דנה", "signature": PNG}},
            "mymop": {"symptom1": "כאב גב", "s1": 5, "wellbeing": 4, "activity_name": "הליכה", "activity": 4}}
    assert p.post("/api/forms", json=body, headers=auth | H).json()["received"]
    assert p.get("/api/forms", headers=auth).status_code == 410   # one use
    card = c.get(f"/api/pm/records/{rid}").json()
    assert {x["kind"] for x in card["consents"]} == {"treatment", "whatsapp"}
    assert card["outcomes"][0]["labels"]["symptom1"] == "כאב גב"
    # a follow-up MYMOP from the clinician keeps the patient's symptom names
    c.post(f"/api/pm/records/{rid}/outcomes", json={"s1": 2, "wellbeing": 2}, headers=H)
    outs = c.get(f"/api/pm/records/{rid}").json()["outcomes"]
    assert outs[-1]["labels"]["symptom1"] == "כאב גב"
    st = c.get("/api/pm/stats").json()
    assert st["mymop"]["mean_change_s1"] == 3
    # a stranger without the link sees nothing
    assert p.get("/api/forms", headers={"Authorization": "Bearer nope"}).status_code == 410


# ---- payments ----
def test_account_balance(env):
    app, _, c = env
    rid = record(c)
    aid = c.post("/api/pm/appointments", json={"record_id": rid, "start": "2026-12-01T10:00", "kind": "first"}, headers=H).json()["appointment"]["id"]
    c.put("/api/pm/prices", json={"kind": "first", "label": "ביקור ראשון", "minutes": 90, "price": 400}, headers=H)
    # the price is fixed at booking time (0 then); set it on a new booking
    aid2 = c.post("/api/pm/appointments", json={"record_id": rid, "start": "2026-12-08T10:00", "kind": "first"}, headers=H).json()["appointment"]["id"]
    for a in (aid, aid2):
        c.put(f"/api/pm/appointments/{a}", json={"status": "done"}, headers=H)
    c.post(f"/api/pm/records/{rid}/packages", json={"label": "סדרת 7", "sessions": 7, "price": 1750}, headers=H)
    acc = c.post(f"/api/pm/records/{rid}/payments", json={"amount": 1000, "method": "bit", "receipt_no": "1234"}, headers=H).json()["account"]
    assert acc["charged"] == 400 + 1750 and acc["paid"] == 1000 and acc["balance"] == 1150


# ---- WhatsApp ----
def test_message_check():
    for k, t in whatsapp.TEMPLATES.items():
        assert whatsapp.check(t["body"]) == [], k
    assert "כאבי" in whatsapp.check("בהמשך לטיפול בכאבי הגב")
    assert whatsapp.check("נשמח לשליחה של הטופס") == []
    assert whatsapp.check("15 דקות לפני") == []
    assert whatsapp.check("קומדין") and whatsapp.check("ההיריון")


def test_manual_whatsapp_link(env):
    _, _, c = env
    rid = record(c)
    aid = c.post("/api/pm/appointments", json={"record_id": rid, "start": "2026-12-01T10:00", "kind": "followup"}, headers=H).json()["appointment"]["id"]
    out = c.post(f"/api/pm/records/{rid}/whatsapp", json={"template": "reminder", "appt_id": aid}, headers=H).json()
    assert out["link"].startswith("https://wa.me/972501234567?text=") and "%D7%93%D7%A0%D7%94" in out["link"]   # "דנה"
    assert "כהן" not in out["text"]   # the first name only


class FakeMeta:
    def __init__(self):
        self.sent = []

    def __call__(self, url, body, headers):
        self.sent.append((url, body, headers))
        return {"messages": [{"id": "wamid.%d" % len(self.sent)}]}


def test_cloud_queue_consent_and_hours(tmp_path):
    app, s, c = build(tmp_path, wa_token="T", wa_phone_id="111", wa_app_secret="sec", wa_verify_token="vt")
    wa = app.state.whatsapp
    wa.http = FakeMeta()
    rid = record(c)
    start = next_weekday(6)
    aid = c.post("/api/pm/appointments", json={"record_id": rid, "start": start.isoformat() + "T16:00", "kind": "followup"}, headers=H).json()["appointment"]["id"]
    due = datetime.fromisoformat((start - timedelta(days=3)).isoformat() + "T10:30").replace(tzinfo=TZ).timestamp()
    # without a WhatsApp consent nothing goes out
    assert wa.run_queue(int(due))["no_consent"] == 1 and not wa.http.sent
    c.post(f"/api/pm/records/{rid}/consents", json={"kind": "whatsapp", "signer": "דנה", "signature": PNG}, headers=H)
    wa.schedule_reminder(aid)
    night = datetime.fromisoformat((start - timedelta(days=3)).isoformat() + "T22:00").replace(tzinfo=TZ).timestamp()
    assert wa.run_queue(int(night))["waiting"] == 1 and not wa.http.sent       # outside the send hours
    assert wa.run_queue(int(due))["sent"] == 1
    url, body, headers = wa.http.sent[0]
    assert url.endswith("/111/messages") and body["to"] == "972501234567" and body["template"]["name"] == "reminder"
    params = [p["text"] for p in body["template"]["components"][0]["parameters"]]
    assert params[0] == "דנה" and params[3] == "16:00"
    # a reply through the webhook: signed, button "confirm" confirms the visit
    hook = {"entry": [{"changes": [{"value": {"messages": [{"id": "in.1", "from": "972501234567", "timestamp": str(int(due) + 60),
                                                           "type": "button", "button": {"payload": "confirm", "text": "מאשר/ת"}}]}}]}]}
    raw = json.dumps(hook).encode()
    sig = "sha256=" + hmac.new(b"sec", raw, hashlib.sha256).hexdigest()
    assert TestClient(app).post("/api/wa/webhook", content=raw, headers={"X-Hub-Signature-256": "sha256=bad"}).status_code == 403
    r = TestClient(app).post("/api/wa/webhook", content=raw, headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"})
    assert r.status_code == 200 and r.json()["messages"] == 1
    assert TestClient(app).post("/api/wa/webhook", content=raw, headers={"X-Hub-Signature-256": sig}).json()["messages"] == 0   # Meta's retry
    assert app.state.practice.get_appt(aid)["status"] == "confirmed"
    # a free-text reply is stored encrypted and waits on the "today" list
    hook["entry"][0]["changes"][0]["value"]["messages"][0] = {"id": "in.2", "from": "972501234567", "timestamp": str(int(due) + 90),
                                                               "type": "text", "text": {"body": "יש לי חום גבוה"}}
    raw = json.dumps(hook).encode()
    TestClient(app).post("/api/wa/webhook", content=raw, headers={"X-Hub-Signature-256": "sha256=" + hmac.new(b"sec", raw, hashlib.sha256).hexdigest()})
    assert c.get(f"/api/pm/records/{rid}").json()["replies"][-1]["text"] == "יש לי חום גבוה"
    assert "חום גבוה".encode() not in s.db_path.read_bytes()
    assert c.get("/api/wa/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "vt", "hub.challenge": "42"}).text == "42"


def test_missed_reminder_shows_on_today(env):
    app, _, c = env
    rid = record(c)
    pm = app.state.practice
    start = datetime.now(TZ) + timedelta(hours=2)
    aid = c.post("/api/pm/appointments", json={"record_id": rid, "start": start.strftime("%Y-%m-%dT%H:%M"), "kind": "followup"}, headers=H).json()["appointment"]["id"]
    # the server was off: the reminder's visit has started before it ran
    app.state.whatsapp.run_queue(int((start + timedelta(minutes=5)).timestamp()))
    t = c.get("/api/pm/today", params={"day": start.date().isoformat()}).json()
    assert any(m["appt_id"] == aid and m["status"] == "missed" for m in t["unsent_messages"])
    manual = c.post(f"/api/pm/queue/{t['unsent_messages'][0]['id']}/manual", headers=H).json()
    assert manual["link"].startswith("https://wa.me/")
    assert pm.today_view(start.date())["appointments"][0]["consent_missing"] == ["treatment", "privacy"]


# ---- Google Calendar ----
class FakeGoogle:
    def __init__(self, rid):
        self.calls = []
        self.events = {"primary": [
            {"id": "g1", "status": "confirmed", "summary": "דנה כהן טיפול", "start": {"dateTime": self.t(2, 9)}, "end": {"dateTime": self.t(2, 10)},
             "extendedProperties": {"private": {"tcm_record": rid}}},
            {"id": "g2", "status": "confirmed", "summary": "פגישה אישית", "start": {"dateTime": self.t(3, 12)}, "end": {"dateTime": self.t(3, 13)}},
            {"id": "g3", "status": "confirmed", "summary": "יום הולדת", "start": {"date": "2030-01-01"}, "end": {"date": "2030-01-02"}},
        ]}

    @staticmethod
    def t(days, hour):
        return (datetime.now(TZ) + timedelta(days=days)).replace(hour=hour, minute=0, second=0, microsecond=0).isoformat()

    def __call__(self, method, url, body=None, headers=None, form=None):
        self.calls.append((method, url, body))
        if url.endswith("/token"):
            return {"access_token": "AT", "refresh_token": "RT", "expires_in": 3600}
        if method == "POST" and url.endswith("/calendars"):
            return {"id": "clinic-cal"}
        if method == "GET" and "/events" in url:
            cal = url.split("/calendars/")[1].split("/events")[0]
            return {"items": self.events.get(cal, [])}
        if method == "POST" and url.endswith("/events"):
            return {"id": "new-%d" % len(self.calls)}
        return {}


def test_google_sync(tmp_path):
    app, s, c = build(tmp_path, google_client_id="cid", google_client_secret="cs")
    rid = record(c)
    gc = app.state.gcal
    fake = FakeGoogle(rid)
    gc.http = fake
    url = c.get("/api/pm/gcal/start").json()["url"]
    state = dict(x.split("=") for x in url.split("?")[1].split("&"))["state"]
    assert c.get("/api/pm/gcal/callback", params={"code": "C", "state": state}, follow_redirects=False).status_code in (302, 307)
    assert gc.connected and b"RT" not in s.db_path.read_bytes()
    c.post("/api/pm/gcal/sync", headers=H)
    appts = app.state.practice.appointments(0, 2 ** 31)
    assert len(appts) == 2   # the all-day event is not a visit
    linked = [a for a in appts if a["record_id"] == rid][0]
    assert linked["external_title"] == "דנה כהן טיפול"
    assert "דנה".encode() not in s.db_path.read_bytes()
    # a series is written to the separate clinic calendar with a neutral title and the record id kept private
    out = c.post(f"/api/pm/records/{rid}/series", json={"start": next_weekday(0).isoformat(), "time": "11:00", "length": 2}, headers=H).json()
    c.post("/api/pm/gcal/sync", headers=H)
    posts = [b for (m, u, b) in fake.calls if m == "POST" and u.endswith("/clinic-cal/events")]
    assert len(posts) == 3 and all(p["summary"] == "טיפול" for p in posts)
    assert posts[0]["extendedProperties"]["private"]["tcm_record"] == rid
    assert not any("followup" in json.dumps(p, ensure_ascii=False) or "דנה" in json.dumps(p, ensure_ascii=False) for p in posts)
    # cancelling one deletes it from Google
    c.put(f"/api/pm/appointments/{out['appointments'][1]}", json={"status": "cancelled"}, headers=H)
    c.post("/api/pm/gcal/sync", headers=H)
    assert any(m == "DELETE" for (m, u, b) in fake.calls)
    assert c.put("/api/pm/gcal/config", json={"title": {"mode": "fixed", "text": "דיקור"}}, headers=H).status_code == 422


# ---- backup ----
def test_backup_and_restore_check(env):
    app, s, c = env
    rid = record(c)
    c.post(f"/api/pm/records/{rid}/notes", json={"note": {"complaint": "בדיקה"}}, headers=H)
    name = c.post("/api/pm/backup", headers=H).json()["file"]
    path = s.data_dir / "backups" / name
    assert path.exists() and b"SQLite" not in path.read_bytes()
    res = c.post("/api/pm/backup/check", headers=H).json()
    assert res["integrity"] == "ok" and res["counts"]["records"] == 1 and res["counts"]["pm_notes"] == 1
    with pytest.raises(Exception):
        bad = bytearray(path.read_bytes()); bad[-1] ^= 1
        path.write_bytes(bytes(bad))
        backup.check(s, path)


def test_today_and_timeline(env):
    app, _, c = env
    rid = record(c)
    now = datetime.now(TZ)
    c.post("/api/pm/appointments", json={"record_id": rid, "start": now.strftime("%Y-%m-%dT%H:%M"), "kind": "followup"}, headers=H)
    c.post(f"/api/pm/records/{rid}/alerts", json={"code": "DEVICE"}, headers=H)
    t = c.get("/api/pm/today", params={"day": now.date().isoformat()}).json()
    assert t["appointments"][0]["name"] == "דנה כהן" and t["appointments"][0]["alerts"] == ["DEVICE"]
    items = c.get(f"/api/pm/records/{rid}/timeline").json()["items"]
    assert {"record", "appointment"} <= {i["type"] for i in items}
    assert c.get("/api/pm/today").status_code == 200
    assert TestClient(app).get("/api/pm/today").status_code == 401
