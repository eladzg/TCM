"""HTTP routes of practice management (see practice.py, whatsapp.py, gcal.py, backup.py) and the
background loop. Every /api/pm route needs the clinician's session; /api/forms takes a one-time patient
link (Bearer), and /api/wa/webhook is Meta's, checked by the app-secret signature instead."""
import json
import threading
import time
from datetime import date, timedelta

from fastapi import Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse, RedirectResponse

from . import backup, forms_he
from .gcal import GoogleCalendar
from .practice import ALERT_CODES, APPT_STATUSES, CONSENT_KINDS, FORM_TASKS, PAY_METHODS, Invalid, Practice
from .whatsapp import TEMPLATES, WhatsApp, check


class Jobs:
    """One loop, once a minute: Google sync every 15 minutes, reminders for upcoming visits, the
    WhatsApp queue, and a backup when the newest is older than a day."""

    def __init__(self, settings, pm, wa, gc):
        self.s, self.pm, self.wa, self.gc = settings, pm, wa, gc
        self.last_gcal = 0
        self.stop = threading.Event()
        self.last = {}

    def tick(self, force_gcal=False):
        out = {}
        if self.gc.connected and (force_gcal or time.time() - self.last_gcal > 900):
            try:
                out["gcal"] = self.gc.sync()
            except Exception as e:  # noqa: BLE001
                out["gcal"] = {"error": str(e)[:200]}
            self.last_gcal = time.time()
        out["reminders_made"] = self.wa.reminders_for_upcoming()
        out["queue"] = self.wa.run_queue()
        age = backup.age_hours(self.s)
        if age is None or age > 24:
            try:
                out["backup"] = str(backup.make(self.s))
            except Exception as e:  # noqa: BLE001
                out["backup"] = {"error": str(e)[:200]}
                self.pm.kv_set("backup_error", str(e)[:200])
        self.last = out
        return out

    def run(self):
        while not self.stop.is_set():
            try:
                self.tick()
            except Exception as e:  # noqa: BLE001 - the loop must survive one bad minute
                self.pm.kv_set("jobs_error", str(e)[:200])
            self.stop.wait(60)


def install(app, store, settings, clinician, body, patient_token):
    pm = Practice(store, settings.timezone)
    wa = WhatsApp(pm, settings)
    gc = GoogleCalendar(pm, settings)
    jobs = Jobs(settings, pm, wa, gc)
    app.state.practice, app.state.whatsapp, app.state.gcal, app.state.jobs = pm, wa, gc, jobs

    def guard(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except Invalid as e:
            raise HTTPException(422, str(e))

    def rec(rid):
        if not store.get_record(rid):
            raise HTTPException(404, "no such record")
        return rid

    # ---- configuration ----
    @app.get("/api/pm/config")
    def config(actor: str = Depends(clinician)):
        last = backup.latest(settings)
        return {
            "kinds": pm.prices(), "statuses": APPT_STATUSES, "alert_codes": ALERT_CODES, "pay_methods": PAY_METHODS,
            "consent_kinds": CONSENT_KINDS, "forms": forms_he.FORMS, "mymop": forms_he.MYMOP, "form_tasks": FORM_TASKS,
            "workdays": pm.workdays(), "days_off": pm.days_off(), "timezone": settings.timezone,
            "whatsapp": wa.config(), "gcal": gc.status(),
            "backup": {"latest": last.name if last else None, "age_hours": backup.age_hours(settings), "error": pm.kv_get("backup_error")},
            "jobs": {"running": settings.run_jobs, "last": jobs.last, "error": pm.kv_get("jobs_error")},
        }

    @app.put("/api/pm/prices")
    async def set_price(request: Request, actor: str = Depends(clinician)):
        d = await body(request)
        guard(pm.set_price, d.get("kind"), d.get("label"), d.get("minutes"), d.get("price"), actor)
        return {"kinds": pm.prices()}

    @app.put("/api/pm/days-off")
    async def day_off(request: Request, actor: str = Depends(clinician)):
        d = await body(request)
        try:
            pm.set_day_off(str(d.get("day")), d.get("label"), actor)
        except ValueError:
            raise HTTPException(422, "day must be YYYY-MM-DD")
        return {"days_off": pm.days_off()}

    @app.put("/api/pm/workdays")
    async def workdays(request: Request, actor: str = Depends(clinician)):
        d = await body(request)
        days = sorted({int(x) for x in d.get("days") or [] if str(x).isdigit() and 0 <= int(x) <= 6})
        if not days:
            raise HTTPException(422, "at least one working day")
        pm.kv_set("workdays", days)
        return {"workdays": days}

    # ---- today and the calendar ----
    @app.get("/api/pm/today")
    def today(day: str = "", actor: str = Depends(clinician)):
        try:
            d = date.fromisoformat(day) if day else None
        except ValueError:
            raise HTTPException(422, "day must be YYYY-MM-DD")
        return pm.today_view(d)

    @app.get("/api/pm/calendar")
    def calendar(start: str = "", days: int = 7, actor: str = Depends(clinician)):
        try:
            d = date.fromisoformat(start) if start else pm.today()
        except ValueError:
            raise HTTPException(422, "start must be YYYY-MM-DD")
        days = max(1, min(days, 42))
        a, _ = pm.day_bounds(d)
        b, _ = pm.day_bounds(d + timedelta(days=days))
        off = pm.days_off(d.year)
        off.update(pm.days_off(d.year + 1))
        return {"start": d.isoformat(), "days": days, "appointments": pm.appointments(a, b),
                "days_off": {k: v for k, v in off.items() if d.isoformat() <= k < (d + timedelta(days=days)).isoformat()},
                "workdays": pm.workdays(), "gcal": gc.status()}

    @app.post("/api/pm/appointments")
    async def add_appt(request: Request, actor: str = Depends(clinician)):
        d = await body(request)
        aid = guard(pm.add_appointment, actor, d.get("record_id") or None, d.get("start"), d.get("kind") or "followup", d.get("minutes"), d.get("package_id"))
        wa.schedule_reminder(aid)
        return {"appointment": pm.get_appt(aid)}

    @app.put("/api/pm/appointments/{aid}")
    async def upd_appt(aid: str, request: Request, actor: str = Depends(clinician)):
        d = await body(request)
        guard(pm.update_appointment, actor, aid, d)
        if "start" in d or "record_id" in d or d.get("status") == "booked":
            wa.schedule_reminder(aid)
        return {"appointment": pm.get_appt(aid)}

    # ---- series ----
    @app.get("/api/pm/series/preview")
    def series_preview(start: str, time: str = "16:00", length: int = 7, per_week: int = 1, actor: str = Depends(clinician)):
        return guard(pm.plan_series, start, time, length, per_week)

    @app.post("/api/pm/records/{rid}/series")
    async def series(rid: str, request: Request, actor: str = Depends(clinician)):
        rec(rid)
        d = await body(request)
        out = guard(pm.create_series, actor, rid, d.get("start"), d.get("time") or "16:00", d.get("length") or 7, d.get("per_week") or 1,
                    d.get("minutes"), d.get("kind") or "followup", d.get("first_kind"), d.get("plan_version"), d.get("package_id"))
        for aid in out["appointments"] + [out["followup"]]:
            wa.schedule_reminder(aid)
        if d.get("send_schedule"):
            wa.enqueue(rid, "series_schedule", extra={"series_id": out["series_id"]})
        return out

    # ---- the patient card ----
    @app.get("/api/pm/records/{rid}")
    def card(rid: str, actor: str = Depends(clinician)):
        rec(rid)
        with store.db() as c:
            store.audit(c, actor, "open_card", rid)
        return {"record_id": rid, "identity": store.get_identity(rid), "record": store.get_record(rid) | {"patient_token_hash": None},
                "alerts": pm.alerts(rid), "notes": pm.notes(rid), "appointments": pm.record_appointments(rid),
                "series": pm.series(rid), "outcomes": pm.outcomes(rid), "consents": pm.consents(rid),
                "account": pm.account(rid), "replies": pm.replies(rid), "queue": wa.queue(rid)}

    @app.post("/api/pm/records/{rid}/notes")
    async def note(rid: str, request: Request, actor: str = Depends(clinician)):
        rec(rid)
        d = await body(request)
        nid, v = guard(pm.save_note, actor, rid, d.get("note") or {}, d.get("note_id"))
        return {"note_id": nid, "version": v}

    @app.get("/api/pm/records/{rid}/notes/{nid}")
    def note_history(rid: str, nid: str, actor: str = Depends(clinician)):
        rec(rid)
        for n in pm.notes(rid, history=True):
            if n["id"] == nid:
                return n
        raise HTTPException(404, "no such note")

    @app.get("/api/pm/records/{rid}/alerts")
    def alerts(rid: str, actor: str = Depends(clinician)):
        rec(rid)
        return {"alerts": pm.alerts(rid, only_active=True)}

    @app.post("/api/pm/records/{rid}/alerts")
    async def alert(rid: str, request: Request, actor: str = Depends(clinician)):
        rec(rid)
        d = await body(request)
        aid = guard(pm.save_alert, actor, rid, d.get("code"), d.get("text") or "", d.get("active", True) is not False, d.get("alert_id"))
        return {"alert_id": aid, "alerts": pm.alerts(rid)}

    @app.post("/api/pm/records/{rid}/outcomes")
    async def outcome(rid: str, request: Request, actor: str = Depends(clinician)):
        rec(rid)
        return {"outcome_id": guard(pm.save_outcome, actor, rid, await body(request))}

    @app.post("/api/pm/records/{rid}/consents")
    async def consent(rid: str, request: Request, actor: str = Depends(clinician)):
        rec(rid)
        d = await body(request)
        kind = d.get("kind")
        if kind not in forms_he.FORMS:
            raise HTTPException(422, "unknown consent")
        return {"consent_id": guard(pm.sign_consent, actor, rid, kind, forms_he.FORMS[kind]["version"], d.get("signer"), d.get("signature"))}

    @app.get("/api/pm/consents/{cid}")
    def consent_doc(cid: str, actor: str = Depends(clinician)):
        with store.db() as c:
            r = c.execute("SELECT record_id FROM pm_consents WHERE id = ?", (cid,)).fetchone()
        if not r:
            raise HTTPException(404, "no such consent")
        for x in pm.consents(r["record_id"], with_signature=True):
            if x["id"] == cid:
                form = forms_he.FORMS.get(x["kind"], {})
                return x | {"title": form.get("title"), "text": form.get("text") if form.get("version") == x["form_version"] else None}
        raise HTTPException(404, "no such consent")

    @app.post("/api/pm/consents/{cid}/revoke")
    def revoke(cid: str, actor: str = Depends(clinician)):
        guard(pm.revoke_consent, actor, cid)
        return {"revoked": cid}

    @app.post("/api/pm/records/{rid}/form-link")
    async def form_link(rid: str, request: Request, actor: str = Depends(clinician)):
        rec(rid)
        d = await body(request)
        token, exp = guard(pm.form_link, actor, rid, d.get("tasks") or [], settings.token_days)
        return {"token": token, "path": "/app/forms.html#" + token, "expires_at": exp}

    @app.post("/api/pm/records/{rid}/packages")
    async def package(rid: str, request: Request, actor: str = Depends(clinician)):
        rec(rid)
        d = await body(request)
        guard(pm.add_package, actor, rid, d.get("label"), d.get("sessions"), d.get("price"))
        return {"account": pm.account(rid)}

    @app.post("/api/pm/records/{rid}/payments")
    async def payment(rid: str, request: Request, actor: str = Depends(clinician)):
        rec(rid)
        d = await body(request)
        guard(pm.add_payment, actor, rid, d.get("amount"), d.get("method"), d.get("receipt_no") or "", d.get("package_id"), d.get("appt_id"), d.get("day"))
        return {"account": pm.account(rid)}

    @app.get("/api/pm/records/{rid}/timeline")
    def timeline(rid: str, actor: str = Depends(clinician)):
        rec(rid)
        return {"items": guard(pm.timeline, rid)}

    # ---- WhatsApp ----
    @app.post("/api/pm/records/{rid}/whatsapp")
    async def wa_manual(rid: str, request: Request, actor: str = Depends(clinician)):
        rec(rid)
        d = await body(request)
        extra = {}
        if d.get("template") == "series_schedule":
            extra["dates"] = wa.series_dates(d.get("series_id") or "")
        if d.get("link_path"):
            extra["link"] = settings.public_base.rstrip("/") + str(d["link_path"])[:200]
        if d.get("link"):
            extra["link"] = str(d["link"])[:300]
        return guard(wa.manual, actor, rid, d.get("template"), d.get("appt_id"), extra)

    @app.post("/api/pm/whatsapp/check")
    async def wa_check(request: Request, actor: str = Depends(clinician)):
        d = await body(request)
        return {"hits": check(str(d.get("text") or "")[:4000])}

    @app.put("/api/pm/whatsapp/config")
    async def wa_config(request: Request, actor: str = Depends(clinician)):
        d = await body(request)
        try:
            wa.set_config(d, actor)
        except (ValueError, TypeError):
            raise HTTPException(422, "bad setting")
        return wa.config()

    @app.get("/api/pm/whatsapp/queue")
    def wa_queue(actor: str = Depends(clinician)):
        return {"queue": wa.queue()}

    @app.post("/api/pm/queue/{qid}/retry")
    def wa_retry(qid: str, actor: str = Depends(clinician)):
        return {"ok": wa.retry(qid, actor)}

    @app.post("/api/pm/queue/{qid}/dismiss")
    def wa_dismiss(qid: str, actor: str = Depends(clinician)):
        wa.dismiss(qid, actor)
        return {"ok": True}

    @app.post("/api/pm/queue/{qid}/manual")
    def wa_queue_manual(qid: str, actor: str = Depends(clinician)):
        with store.db() as c:
            q = c.execute("SELECT * FROM pm_queue WHERE id = ?", (qid,)).fetchone()
        if not q:
            raise HTTPException(404, "no such message")
        extra = json.loads(q["params"] or "{}")
        if q["template"] == "series_schedule":
            extra["dates"] = wa.series_dates(extra.get("series_id", ""))
        out = guard(wa.manual, actor, q["record_id"], q["template"], q["appt_id"], extra)
        if out.get("link"):
            with store.db() as c:
                c.execute("UPDATE pm_queue SET status = 'sent_by_hand' WHERE id = ?", (qid,))
        return out

    @app.post("/api/pm/replies/{iid}/handled")
    def reply_handled(iid: str, actor: str = Depends(clinician)):
        guard(pm.handle_reply, actor, iid)
        return {"ok": True}

    @app.get("/api/wa/webhook")
    def wa_verify(request: Request):
        q = request.query_params
        got = wa.verify_get(q.get("hub.mode"), q.get("hub.verify_token"), q.get("hub.challenge"))
        if got is None:
            raise HTTPException(403, "verification failed")
        return PlainTextResponse(got)

    @app.post("/api/wa/webhook")
    async def wa_hook(request: Request):
        raw = await request.body()
        if len(raw) > 1024 * 1024 or not wa.signature_ok(raw, request.headers.get("x-hub-signature-256", "")):
            raise HTTPException(403, "bad signature")
        try:
            payload = json.loads(raw)
        except ValueError:
            raise HTTPException(400, "invalid JSON")
        return wa.take_in(payload)

    # ---- Google Calendar ----
    @app.get("/api/pm/gcal/start")
    def gcal_start(actor: str = Depends(clinician)):
        return {"url": guard(gc.auth_url)}

    @app.get("/api/pm/gcal/callback")
    def gcal_callback(code: str = "", state: str = "", error: str = "", actor: str = Depends(clinician)):
        if error:
            return RedirectResponse("/app/index.html#pm-admin")
        try:
            gc.callback(code, state)
            jobs.tick(force_gcal=True)
        except Invalid as e:
            raise HTTPException(422, str(e))
        return RedirectResponse("/app/index.html#pm-admin")

    @app.post("/api/pm/gcal/sync")
    def gcal_sync(actor: str = Depends(clinician)):
        if not gc.connected:
            raise HTTPException(409, "Google Calendar is not connected")
        try:
            out = gc.sync()
        except Exception as e:  # noqa: BLE001
            raise HTTPException(502, str(e)[:300])
        wa.reminders_for_upcoming()
        return out

    @app.put("/api/pm/gcal/config")
    async def gcal_config(request: Request, actor: str = Depends(clinician)):
        guard(gc.set_config, await body(request))
        return gc.status()

    @app.post("/api/pm/gcal/disconnect")
    def gcal_disconnect(actor: str = Depends(clinician)):
        gc.disconnect()
        return gc.status()

    # ---- statistics and backup ----
    @app.get("/api/pm/stats")
    def stats(actor: str = Depends(clinician)):
        return pm.stats()

    @app.post("/api/pm/backup")
    def make_backup(actor: str = Depends(clinician)):
        try:
            path = backup.make(settings)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(500, "backup failed: " + str(e)[:200])
        pm.kv_set("backup_error", None)
        with store.db() as c:
            store.audit(c, actor, "backup")
        return {"file": path.name}

    @app.post("/api/pm/backup/check")
    def check_backup(actor: str = Depends(clinician)):
        last = backup.latest(settings)
        if not last:
            raise HTTPException(404, "no backup yet")
        try:
            return backup.check(settings, last)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(500, "the backup did not open: " + str(e)[:200])

    # ---- patient forms (consent and MYMOP) ----
    @app.get("/api/forms")
    def forms_open(token: str = Depends(patient_token)):
        info = pm.form_for_token(token)
        if not info:
            raise HTTPException(410, "this link is closed or expired")
        return {"tasks": info["tasks"], "expires_at": info["expires_at"],
                "forms": {k: forms_he.FORMS[k] for k in CONSENT_KINDS if "consent:" + k in info["tasks"]},
                "mymop": forms_he.MYMOP if "mymop" in info["tasks"] else None,
                "mymop_labels": info.get("mymop_labels") or {}}

    @app.post("/api/forms")
    async def forms_submit(request: Request, token: str = Depends(patient_token)):
        d = await body(request)
        try:
            rid = pm.submit_forms(token, d, forms_he.FORMS)
        except Invalid as e:
            raise HTTPException(422, str(e))
        if not rid:
            raise HTTPException(410, "this link is closed or expired")
        return {"received": True}

    return jobs
