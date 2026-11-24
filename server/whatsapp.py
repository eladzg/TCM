"""WhatsApp: fixed logistic templates, the clinical-word check, wa.me links, the reminder queue,
sending through the WhatsApp Cloud API and taking in replies from its webhook.

The privacy line: Meta is an outside service and every message names a phone number, so a message
may carry only logistics (a first name, a day and time, the clinic's address, a one-time link). Every
template and every parameter except the name, address and link passes `check()` before anything is
sent, and a hit blocks the send. With the Cloud API Meta processes the message text, so automatic
reminders go only to records with a signed, unrevoked WhatsApp consent. The log keeps the template
id, never the text.

Sending needs TCM_WA_TOKEN and TCM_WA_PHONE_ID; without them the queue stays local and the "today"
list offers the same message as a wa.me link the clinician sends by hand. Replies: the clinic's number
runs in the WhatsApp Business app and the Cloud API together (Meta's "coexistence"), so the clinician
sees replies on the phone as usual, and Meta posts a copy to /api/wa/webhook. Meta retries a webhook
for some days while the server is off, so replies arrive when it starts. Only that path should be
reachable from outside (see docs/practice-setup.md).
"""
import hashlib
import hmac
import json
import re
import secrets
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, time as dtime, timedelta
from pathlib import Path

from .practice import Invalid, new_id
from .store import now

ROOT = Path(__file__).resolve().parent.parent
WEEKDAYS_HE = ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"]  # Python weekday() order

# Each template: the Hebrew body with {named} slots, the order Meta numbers them ({{1}}, {{2}}...),
# and quick-reply buttons. "meta_name" is the template's name as approved in WhatsApp Manager.
TEMPLATES = {
    "appt_confirm": {
        "label": "אישור תור",
        "body": "שלום {name}, נקבע לך תור ביום {weekday} {date} בשעה {time}.\nכתובת: {address}\nלשינוי או ביטול אפשר להשיב להודעה זו.",
        "params": ["name", "weekday", "date", "time", "address"],
        "buttons": [],
    },
    "reminder": {
        "label": "תזכורת לתור",
        "body": "שלום {name}, תזכורת לתור ביום {weekday} {date} בשעה {time}.\nנשמח לאישור בלחיצה על הכפתור.",
        "params": ["name", "weekday", "date", "time"],
        "buttons": [{"id": "confirm", "text": "מאשר/ת"}, {"id": "change", "text": "צריך לשנות"}],
    },
    "intake_link": {
        "label": "קישור לשאלון",
        "body": "שלום {name}, לפני הפגישה הראשונה נשמח שתמלא/י שאלון קצר בקישור {link}\nהקישור אישי ונסגר אחרי השליחה.",
        "params": ["name", "link"],
        "buttons": [],
    },
    "forms_link": {
        "label": "קישור לטפסים",
        "body": "שלום {name}, לפני הפגישה נשמח שתמלא/י טופס קצר בקישור {link}\nהקישור אישי ונסגר אחרי השליחה.",
        "params": ["name", "link"],
        "buttons": [],
    },
    "series_schedule": {
        "label": "מועדי המפגשים",
        "body": "שלום {name}, אלה מועדי המפגשים שקבענו: {dates}.\nלשינוי אפשר להשיב להודעה זו.",
        "params": ["name", "dates"],
        "buttons": [],
    },
    "followup_check": {
        "label": "בדיקת שלומך",
        "body": "שלום {name}, עברו שבועיים מהמפגש האחרון. נשמח לשמוע מה שלומך ואם תרצה/י לקבוע מפגש המשך.",
        "params": ["name"],
        "buttons": [],
    },
}
FREE_PARAMS = {"name", "address", "link"}   # names, the clinic address and a URL are not checked for clinical words

# The closed dictionary: words that make a message clinical. The interview lexicon's Hebrew words and the
# safety terms are added at load time.
BASE_TERMS = [
    "כאב", "כאבי", "כאבים", "כואב", "שינה", "נדודי", "דיכאון", "חרדה", "לחץ דם", "סוכרת", "הריון", "היריון", "פוריות",
    "מחזור", "וסת", "עיכול", "תסמונת", "תבנית", "אבחנה", "אבחון", "מחלה", "מחלת", "תרופה", "תרופות", "צמח", "צמחים",
    "פורמולה", "מרשם", "דיקור", "מחטים", "מחט", "כוסות רוח", "מוקסה", "נקודה", "נקודות", "לשון", "דופק", "כבד", "טחול",
    "כליות", "כליה", "יין", "יאנג", "צ׳י", "צ'י", "ליחה", "לחות", "סטגנציה", "חסר", "גודש", "תסמין", "תסמינים",
    "טיפול ב", "תוכנית הטיפול", "תכנית הטיפול", "שאלון רפואי", "בדיקת דם", "הקאות", "שלשול", "עצירות", "מיגרנה",
    "פוסט טראומה", "סרטן", "כימותרפיה", "גב", "ברך", "צוואר", "כתף",
]
PREFIX = "[ובהלמשכ]{0,3}"


def _terms():
    terms = set(BASE_TERMS)
    try:
        import yaml
        lex = yaml.safe_load((ROOT / "kb/lexicon/interview_features.yaml").read_text(encoding="utf-8"))
        for f in lex.get("features") or []:
            terms.update(w for w in (f.get("syn_he") or []) if isinstance(w, str))
            if f.get("label_he"):
                terms.add(f["label_he"])
        safety = yaml.safe_load((ROOT / "kb/lexicon/interview_safety.yaml").read_text(encoding="utf-8"))
        for rule in safety.get("constraint_terms") or []:
            terms.update(t for t in rule.get("terms") or [] if re.search("[֐-׿]", t))
    except (OSError, ImportError, AttributeError):
        pass
    return sorted({t.strip() for t in terms if t and t.strip()}, key=len, reverse=True)


TERMS = _terms()
_RX = []
for _t in TERMS:
    body = re.escape(_t)
    # Short words (2-3 letters) must be whole words, so "דק" does not catch "דקות".
    tail = r"(?![֐-׿])" if len(_t) <= 3 else ""
    _RX.append((_t, re.compile(r"(?:^|(?<![֐-׿]))" + PREFIX + body + tail)))


# Ordinary logistic words that merely contain a dictionary word after a prefix letter (ש+ליחה).
ALLOW = {"שליחה", "שליחת", "השליחה", "בשליחה", "לשליחה", "משליחה", "שליחות"}
_WORD = re.compile(r"[\u0590-\u05FF'׳]+")


def check(text):
    """The clinical words found in `text` (empty list = the message is logistics only)."""
    text = str(text or "")
    found = []
    for term, rx in _RX:
        if any(term in f for f in found):
            continue
        for m in rx.finditer(text):
            w = _WORD.search(text, m.start())
            if w and w.group(0) in ALLOW:
                continue
            found.append(term)
            break
    return found


def render(template, params):
    t = TEMPLATES.get(template)
    if not t:
        raise Invalid("unknown template")
    missing = [p for p in t["params"] if not str(params.get(p) or "").strip()]
    if missing:
        raise Invalid("missing " + ", ".join(missing))
    hits = check(t["body"]) + [w for p in t["params"] if p not in FREE_PARAMS for w in check(params.get(p))]
    text = t["body"].format(**{p: str(params.get(p)) for p in t["params"]})
    return text, hits


def meta_param(v):
    """Meta refuses a template parameter with a line break, a tab or more than four spaces in a row."""
    v = re.sub(r"[\r\n\t]+", " · ", str(v))
    return re.sub(r" {4,}", "   ", v).strip()


EXAMPLES = {"name": "דנה", "weekday": "שלישי", "date": "08.12", "time": "16:00", "address": "רחוב הרצל 1, תל אביב",
            "link": "https://example.org/app/patient.html", "dates": "שלישי 08.12 16:00 · שלישי 15.12 16:00"}


def template_definition(key, name, lang="he"):
    """The body Meta's /message_templates endpoint takes: {name} slots become {{1}}, {{2}}... with examples."""
    t = TEMPLATES[key]
    text = t["body"]
    for i, p in enumerate(t["params"], 1):
        text = text.replace("{" + p + "}", "{{" + str(i) + "}}")
    comps = [{"type": "BODY", "text": text, "example": {"body_text": [[EXAMPLES[p] for p in t["params"]]]}}]
    if t["buttons"]:
        comps.append({"type": "BUTTONS", "buttons": [{"type": "QUICK_REPLY", "text": b["text"]} for b in t["buttons"]]})
    return {"name": name, "language": lang, "category": "UTILITY", "components": comps}


def normalize_phone(phone):
    digits = re.sub(r"\D", "", str(phone or ""))
    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("0"):
        digits = "972" + digits[1:]
    return digits if 9 <= len(digits) <= 15 else ""


def wa_link(phone, text):
    p = normalize_phone(phone)
    if not p:
        raise Invalid("no usable phone number on this record")
    return "https://wa.me/" + p + "?text=" + urllib.parse.quote(text)


def first_name(identity):
    name = ((identity or {}).get("name") or "").strip()
    return name.split()[0] if name else ""


class WhatsApp:
    def __init__(self, practice, settings, http=None, http_get=None):
        self.pm = practice
        self.s = settings
        self.http = http or _post_json
        self.http_get = http_get or _get_json

    @property
    def graph(self):
        return f"{self.s.wa_api_base}/{self.s.wa_api_version}"

    def _auth(self):
        return {"Authorization": "Bearer " + self.s.wa_token}

    # ---- configuration ----
    @property
    def cloud(self):
        return bool(self.s.wa_token and self.s.wa_phone_id)

    def config(self):
        names = self.pm.kv_get("wa_meta_names", {})
        return {
            "cloud_api": self.cloud,
            "test_mode": bool(getattr(self.s, "wa_test_mode", False)),
            "webhook": bool(self.s.wa_verify_token and self.s.wa_app_secret),
            "send_hours": self.send_hours(),
            "reminder_time": self.pm.kv_get("wa_reminder_time", "10:00"),
            "address": self.pm.kv_get("clinic_address", ""),
            "lang": self.pm.kv_get("wa_lang", "he"),
            "templates": [{"id": k, "label": t["label"], "body": t["body"], "params": t["params"],
                           "buttons": t["buttons"], "meta_name": names.get(k, k), "check": check(t["body"])}
                          for k, t in TEMPLATES.items()],
        }

    def send_hours(self):
        return self.pm.kv_get("wa_send_hours", ["09:00", "19:00"])

    def set_config(self, data, actor):
        if "send_hours" in data:
            a, b = data["send_hours"]
            for x in (a, b):
                datetime.strptime(x, "%H:%M")
            self.pm.kv_set("wa_send_hours", [a, b])
        if "reminder_time" in data:
            datetime.strptime(data["reminder_time"], "%H:%M")
            self.pm.kv_set("wa_reminder_time", data["reminder_time"])
        if "address" in data:
            self.pm.kv_set("clinic_address", str(data["address"])[:200])
        if "meta_names" in data and isinstance(data["meta_names"], dict):
            clean = {k: re.sub(r"[^a-z0-9_]", "", str(v).lower())[:60] for k, v in data["meta_names"].items() if k in TEMPLATES}
            self.pm.kv_set("wa_meta_names", clean)
        with self.pm.db() as c:
            self.pm.audit(c, actor, "wa_config")

    # ---- parameters for a record and an appointment ----
    def params_for(self, rid, appt_id=None, extra=None):
        with self.pm.db() as c:
            ident = self.pm.store._get_identity(c, rid) or {}
        p = {"name": first_name(ident), "address": self.pm.kv_get("clinic_address", "")}
        if appt_id:
            a = self.pm.get_appt(appt_id)
            if a:
                d = datetime.strptime(a["start"], "%Y-%m-%dT%H:%M")
                p.update(weekday=WEEKDAYS_HE[d.weekday()], date=d.strftime("%d.%m"), time=d.strftime("%H:%M"))
        p.update(extra or {})
        return p, ident.get("phone")

    def series_dates(self, series_id):
        with self.pm.db() as c:
            rows = c.execute("SELECT start FROM pm_appointments WHERE series_id = ? AND status != 'cancelled' ORDER BY start", (series_id,)).fetchall()
        out = []
        for r in rows:
            d = self.pm.local(r["start"])
            out.append(f"{WEEKDAYS_HE[d.weekday()]} {d.strftime('%d.%m')} {d.strftime('%H:%M')}")
        return " · ".join(out)

    def log(self, c, rid, template, channel, status):
        c.execute("INSERT INTO pm_messages (record_id, template, channel, at, status) VALUES (?, ?, ?, ?, ?)", (rid, template, channel, now(), status))

    # ---- the clinician sends by hand ----
    def manual(self, actor, rid, template, appt_id=None, extra=None):
        params, phone = self.params_for(rid, appt_id, extra)
        text, hits = render(template, params)
        if hits:
            return {"blocked": hits, "text": text}
        link = wa_link(phone, text)
        with self.pm.db() as c:
            self.log(c, rid, template, "wa.me", "opened")
            self.pm.audit(c, actor, "wa_manual:" + template, rid)
        return {"blocked": [], "text": text, "link": link}

    # ---- a send the clinician asks for: through the Cloud API when it is set up ----
    def direct(self, actor, rid, template, appt_id=None, extra=None):
        """With the Cloud API set up, the message goes from the clinic's number; otherwise (or when Meta
        refuses it) the answer carries the wa.me link for sending by hand, and says why. On Meta's test
        number the Hebrew text goes as a plain message, which Meta delivers only within 24 hours of the
        recipient's last message to the number: no hello_world stand-in here, since a link must arrive whole."""
        if not self.cloud:
            return self.manual(actor, rid, template, appt_id, extra)
        params, phone = self.params_for(rid, appt_id, extra)
        text, hits = render(template, params)
        if hits:
            return {"blocked": hits, "text": text}
        to = normalize_phone(phone)
        reason = None
        if not to:
            reason = "no usable phone number in the record"
        else:
            try:
                if getattr(self.s, "wa_test_mode", False):
                    body = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": text, "preview_url": False}}
                    res = self.http(f"{self.graph}/{self.s.wa_phone_id}/messages", body, self._auth())
                    mid = ((res or {}).get("messages") or [{}])[0].get("id")
                else:
                    mid = self.send_template(phone, template, params)
            except Exception as e:  # noqa: BLE001 - Meta's reason goes back to the screen, with the manual link
                reason = str(e)[:400]
            else:
                with self.pm.db() as c:
                    self.log(c, rid, template, "cloud_api", "sent")
                    self.pm.audit(c, actor, "wa_direct:" + template, rid)
                return {"blocked": [], "sent": True, "id": mid, "text": text, "test_mode": bool(getattr(self.s, "wa_test_mode", False))}
        out = self.manual(actor, rid, template, appt_id, extra)
        out["sent"] = False
        out["error"] = reason
        return out

    # ---- the reminder queue ----
    def schedule_reminder(self, appt_id):
        """Queue the reminder for the working day before the visit, at the reminder time (10:00 by
        default). A Sunday visit is reminded on Thursday. It stays valid until the visit starts."""
        a = self.pm.get_appt(appt_id)
        if not a or not a["record_id"] or a["status"] in ("cancelled", "done", "no_show"):
            return None
        start = datetime.strptime(a["start"], "%Y-%m-%dT%H:%M")
        day = self.pm.previous_workday(start.date())
        hh, mm = map(int, self.pm.kv_get("wa_reminder_time", "10:00").split(":"))
        due = int(datetime.combine(day, dtime(hh, mm), tzinfo=self.pm.tz).timestamp())
        qid = new_id("Q")
        with self.pm.db() as c:
            c.execute("UPDATE pm_queue SET status = 'cancelled' WHERE appt_id = ? AND template = 'reminder' AND status = 'pending'", (appt_id,))
            c.execute("INSERT INTO pm_queue (id, record_id, appt_id, template, params, due_at, not_after, status, created_at) "
                      "VALUES (?, ?, ?, 'reminder', '{}', ?, ?, 'pending', ?)", (qid, a["record_id"], appt_id, due, a["ts"], now()))
        return {"id": qid, "due": self.pm.fmt(due)}

    def enqueue(self, rid, template, appt_id=None, extra=None, due=None):
        qid = new_id("Q")
        with self.pm.db() as c:
            c.execute("INSERT INTO pm_queue (id, record_id, appt_id, template, params, due_at, not_after, status, created_at) "
                      "VALUES (?, ?, ?, ?, ?, ?, NULL, 'pending', ?)", (qid, rid, appt_id, template, json.dumps(extra or {}, ensure_ascii=False), due or now(), now()))
        return qid

    def reminders_for_upcoming(self, days=14):
        """Make sure every upcoming visit of a record has a pending reminder (new visits from Google too)."""
        made = 0
        with self.pm.db() as c:
            rows = c.execute("SELECT a.id FROM pm_appointments a WHERE a.record_id IS NOT NULL AND a.status IN ('booked') "
                             "AND a.start BETWEEN ? AND ? AND NOT EXISTS (SELECT 1 FROM pm_queue q WHERE q.appt_id = a.id AND q.template = 'reminder')",
                             (now(), now() + days * 86400)).fetchall()
        for r in rows:
            if self.schedule_reminder(r["id"]):
                made += 1
        return made

    def in_send_hours(self, at=None):
        t = datetime.fromtimestamp(at or now(), self.pm.tz)
        a, b = self.send_hours()
        return a <= t.strftime("%H:%M") < b and self.pm.is_workday(t.date())

    def run_queue(self, at=None):
        """Send what is due, inside the send hours. A reminder whose visit has started is 'missed' and
        shows on the "today" list. Returns counts."""
        at = at or now()
        out = {"sent": 0, "failed": 0, "missed": 0, "no_consent": 0, "blocked": 0, "waiting": 0}
        with self.pm.db() as c:
            c.execute("UPDATE pm_queue SET status = 'missed' WHERE status = 'pending' AND not_after IS NOT NULL AND not_after <= ?", (at,))
            out["missed"] = c.total_changes
            due = c.execute("SELECT * FROM pm_queue WHERE status = 'pending' AND due_at <= ? ORDER BY due_at LIMIT 50", (at,)).fetchall()
        if not due:
            return out
        if not self.cloud or not self.in_send_hours(at):
            out["waiting"] = len(due)
            return out
        for q in due:
            with self.pm.db() as c:
                ok = q["record_id"] and self.pm.has_consent(c, q["record_id"], "whatsapp")
                if not ok:
                    c.execute("UPDATE pm_queue SET status = 'skipped_no_consent' WHERE id = ?", (q["id"],))
                    out["no_consent"] += 1
                    continue
            params, phone = self.params_for(q["record_id"], q["appt_id"], json.loads(q["params"] or "{}"))
            if q["template"] == "series_schedule" and "dates" not in params:
                params["dates"] = self.series_dates(params.get("series_id", ""))
            status, err, mid = "failed", None, None
            try:
                text, hits = render(q["template"], params)
                if hits:
                    status, err = "blocked", "clinical words: " + ", ".join(hits)
                    out["blocked"] += 1
                else:
                    mid = self.send_template(phone, q["template"], params)
                    status = "sent"
                    out["sent"] += 1
            except Exception as e:  # noqa: BLE001 - any failure stays visible on the "today" list
                err = str(e)[:300]
                out["failed"] += 1
            with self.pm.db() as c:
                c.execute("UPDATE pm_queue SET status = ?, tries = tries + 1, last_error = ?, wa_message_id = ?, sent_at = ? WHERE id = ?",
                          (status if status != "failed" or q["tries"] >= 2 else "pending", err, mid, now() if status == "sent" else None, q["id"]))
                if status == "failed" and q["tries"] < 2:
                    c.execute("UPDATE pm_queue SET due_at = ? WHERE id = ?", (at + 600, q["id"]))
                self.log(c, q["record_id"], q["template"], "cloud_api", status)
        return out

    def send_template(self, phone, template, params):
        to = normalize_phone(phone)
        if not to:
            raise Invalid("no usable phone number")
        t = TEMPLATES[template]
        if getattr(self.s, "wa_test_mode", False):
            return self.send_test_mode(to, template, params)
        names = self.pm.kv_get("wa_meta_names", {})
        comps = [{"type": "body", "parameters": [{"type": "text", "text": meta_param(params[p])} for p in t["params"]]}]
        for i, b in enumerate(t["buttons"]):
            comps.append({"type": "button", "sub_type": "quick_reply", "index": str(i), "parameters": [{"type": "payload", "payload": b["id"]}]})
        body = {"messaging_product": "whatsapp", "to": to, "type": "template",
                "template": {"name": names.get(template, template), "language": {"code": self.pm.kv_get("wa_lang", "he")}, "components": comps}}
        res = self.http(f"{self.graph}/{self.s.wa_phone_id}/messages", body, self._auth())
        return ((res or {}).get("messages") or [{}])[0].get("id")

    def send_test_mode(self, to, template, params):
        """Meta's developer test number, for a demo without a business: no approved templates there, so the
        Hebrew text goes as a plain message. Meta allows that only within 24 hours of the recipient's last
        message to the number; outside that window it refuses, and the approved "hello_world" goes instead,
        so a reminder still visibly arrives. Recipients must be on the app's list of up to five test numbers."""
        text, _ = render(template, params)
        body = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": text, "preview_url": False}}
        try:
            res = self.http(f"{self.graph}/{self.s.wa_phone_id}/messages", body, self._auth())
        except MetaError:
            res = self.http(f"{self.graph}/{self.s.wa_phone_id}/messages", {"messaging_product": "whatsapp", "to": to, "type": "template",
                            "template": {"name": "hello_world", "language": {"code": "en_US"}}}, self._auth())
        return ((res or {}).get("messages") or [{}])[0].get("id")

    # ---- checking the connection ----
    def status(self):
        """Ask Meta about the configured number: proves the token and the phone number id work."""
        if not self.cloud:
            return {"ok": False, "error": "TCM_WA_TOKEN and TCM_WA_PHONE_ID are not set"}
        try:
            n = self.http_get(f"{self.graph}/{self.s.wa_phone_id}?fields=display_phone_number,verified_name,quality_rating,"
                              "code_verification_status,name_status,messaging_limit_tier", self._auth())
        except Exception as e:  # noqa: BLE001 - shown on the management screen
            return {"ok": False, "error": str(e)[:400]}
        out = {"ok": True, "number": n.get("display_phone_number"), "name": n.get("verified_name"), "quality": n.get("quality_rating"),
               "name_status": n.get("name_status"), "limit": n.get("messaging_limit_tier"), "templates": None}
        if self.s.wa_waba_id:
            try:
                out["templates"] = self.meta_templates()
            except Exception as e:  # noqa: BLE001
                out["templates_error"] = str(e)[:400]
        return out

    def meta_templates(self):
        """The account's templates as Meta sees them (name, language, status, category)."""
        r = self.http_get(f"{self.graph}/{self.s.wa_waba_id}/message_templates?fields=name,language,status,category,rejected_reason&limit=200", self._auth())
        return [{k: t.get(k) for k in ("name", "language", "status", "category", "rejected_reason")} for t in (r or {}).get("data") or []]

    def submit_templates(self, only=None):
        """Send the six templates to Meta for approval (category Utility, Hebrew). Returns Meta's answer per template."""
        if not (self.s.wa_token and self.s.wa_waba_id):
            raise Invalid("TCM_WA_TOKEN and TCM_WA_WABA_ID are needed to submit templates")
        names = self.pm.kv_get("wa_meta_names", {})
        out = []
        for k, t in TEMPLATES.items():
            if only and k not in only:
                continue
            body = template_definition(k, names.get(k, k), self.pm.kv_get("wa_lang", "he"))
            try:
                r = self.http(f"{self.graph}/{self.s.wa_waba_id}/message_templates", body, self._auth())
                out.append({"template": k, "name": body["name"], "id": r.get("id"), "status": r.get("status"), "category": r.get("category")})
            except Exception as e:  # noqa: BLE001 - one bad template should not stop the others
                out.append({"template": k, "name": body["name"], "error": str(e)[:400]})
        return out

    def send_test(self, phone):
        """Meta's own "hello_world" template (English, approved in every new account): checks sending end to end."""
        to = normalize_phone(phone)
        if not to:
            raise Invalid("no usable phone number")
        body = {"messaging_product": "whatsapp", "to": to, "type": "template", "template": {"name": "hello_world", "language": {"code": "en_US"}}}
        res = self.http(f"{self.graph}/{self.s.wa_phone_id}/messages", body, self._auth())
        return {"id": ((res or {}).get("messages") or [{}])[0].get("id")}

    def retry(self, qid, actor):
        with self.pm.db() as c:
            n = c.execute("UPDATE pm_queue SET status = 'pending', due_at = ?, tries = 0, not_after = CASE WHEN not_after < ? THEN NULL ELSE not_after END "
                          "WHERE id = ? AND status IN ('failed', 'missed', 'blocked')", (now(), now(), qid)).rowcount
            self.pm.audit(c, actor, "wa_retry:" + qid)
        return bool(n)

    def dismiss(self, qid, actor):
        with self.pm.db() as c:
            c.execute("UPDATE pm_queue SET status = 'dismissed' WHERE id = ?", (qid,))
            self.pm.audit(c, actor, "wa_dismiss:" + qid)

    def queue(self, rid=None):
        with self.pm.db() as c:
            q = "SELECT id, record_id, appt_id, template, due_at, status, last_error, sent_at FROM pm_queue"
            rows = c.execute(q + (" WHERE record_id = ?" if rid else "") + " ORDER BY due_at DESC LIMIT 200", (rid,) if rid else ()).fetchall()
        return [dict(r) | {"due": self.pm.fmt(r["due_at"])} for r in rows]

    # ---- the webhook ----
    def verify_get(self, mode, token, challenge):
        if mode == "subscribe" and self.s.wa_verify_token and hmac.compare_digest(str(token or ""), self.s.wa_verify_token):
            return challenge
        return None

    def signature_ok(self, raw, header):
        if not self.s.wa_app_secret or not header or not header.startswith("sha256="):
            return False
        want = hmac.new(self.s.wa_app_secret.encode(), raw, hashlib.sha256).hexdigest()
        return hmac.compare_digest(want, header[7:])

    def record_for_phone(self, phone):
        p = normalize_phone(phone)
        if not p:
            return None
        with self.pm.db() as c:
            for r in c.execute("SELECT record_id FROM identities"):
                ident = self.pm.store._get_identity(c, r["record_id"]) or {}
                if normalize_phone(ident.get("phone")) == p:
                    return r["record_id"]
        return None

    def take_in(self, payload):
        """Store replies and delivery statuses from one webhook post. Returns counts."""
        out = {"messages": 0, "statuses": 0}
        for entry in (payload or {}).get("entry") or []:
            for ch in entry.get("changes") or []:
                v = ch.get("value") or {}
                for st in v.get("statuses") or []:
                    with self.pm.db() as c:
                        n = c.execute("UPDATE pm_queue SET status = CASE WHEN ? = 'failed' THEN 'failed' ELSE status END, "
                                      "last_error = CASE WHEN ? = 'failed' THEN 'delivery failed' ELSE last_error END WHERE wa_message_id = ?",
                                      (st.get("status"), st.get("status"), st.get("id"))).rowcount
                        out["statuses"] += n
                for m in v.get("messages") or []:
                    out["messages"] += self._message(m)
        return out

    def _message(self, m):
        mid = str(m.get("id") or "")[:200]
        with self.pm.db() as c:
            if mid and c.execute("SELECT 1 FROM pm_inbound WHERE wa_message_id = ?", (mid,)).fetchone():
                return 0
        rid = self.record_for_phone(m.get("from"))
        kind, payload, text = "text", None, ""
        if m.get("type") == "button":
            kind, payload, text = "button", (m.get("button") or {}).get("payload"), (m.get("button") or {}).get("text", "")
        elif m.get("type") == "interactive":
            br = (m.get("interactive") or {}).get("button_reply") or {}
            kind, payload, text = "button", br.get("id"), br.get("title", "")
        elif m.get("type") == "text":
            text = (m.get("text") or {}).get("body", "")
        else:
            kind = str(m.get("type") or "other")[:20]
        if payload not in (None, "confirm", "change"):
            payload = None
        at = int(m.get("timestamp") or now())
        iid = new_id("I")
        appt = None
        with self.pm.db() as c:
            if rid:
                # The reply is about the next visit whose reminder went out.
                row = c.execute("SELECT q.appt_id FROM pm_queue q JOIN pm_appointments a ON a.id = q.appt_id WHERE q.record_id = ? AND q.status = 'sent' "
                                "AND a.start > ? ORDER BY a.start LIMIT 1", (rid, at - 3600)).fetchone()
                appt = row["appt_id"] if row else None
            kid, nonce, blob = self.pm.seal("data", {"text": str(text)[:4000]}, f"inbound|{iid}")
            fk = fn = fb = None
            if not rid:
                fk, fn, fb = self.pm.seal("identity", {"from": str(m.get("from"))[:20]}, f"inbound|{iid}|from")
            handled = 0
            if appt and payload == "confirm":
                c.execute("UPDATE pm_appointments SET status = 'confirmed', updated_at = ? WHERE id = ? AND status = 'booked'", (now(), appt))
                handled = 1
            elif appt and payload == "change":
                c.execute("UPDATE pm_appointments SET status = 'change_requested', updated_at = ? WHERE id = ?", (now(), appt))
            c.execute("INSERT INTO pm_inbound VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                      (iid, rid, at, mid or None, kind, payload, appt, handled, kid, nonce, blob, fk, fn, fb))
            self.pm.audit(c, "whatsapp", "reply:" + (payload or kind), rid)
        return 1


class MetaError(Exception):
    pass


def _open(req):
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        # Meta explains a refusal in the body: {"error": {"message", "code", "error_data": {"details"}}}.
        try:
            err = json.loads(e.read().decode("utf-8") or "{}").get("error") or {}
        except ValueError:
            err = {}
        detail = (err.get("error_data") or {}).get("details") or err.get("error_user_msg") or err.get("message") or e.reason
        hint = {100: "Meta does not know this id: is TCM_WA_PHONE_ID the Phone number ID from API Setup, not the phone number itself? ",
                190: "The token expired or is wrong: make a new one. ",
                131030: "This number is not on the test number's recipient list (API Setup, To). ",
                131047: "More than 24 hours since the recipient last wrote to this number, so Meta allows only an approved template. "}.get(err.get("code"), "")
        raise MetaError(hint + f"Meta {e.code}" + (f" (code {err.get('code')})" if err.get("code") else "") + f": {detail}") from None


def _post_json(url, body, headers):
    return _open(urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST",
                                        headers={"Content-Type": "application/json", **headers}))


def _get_json(url, headers):
    return _open(urllib.request.Request(url, method="GET", headers=headers))


def new_verify_token():
    return secrets.token_urlsafe(24)
