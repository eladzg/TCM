"""The clinic server.

    uvicorn server.app:app --host 127.0.0.1 --port 8000

Two sides with separate credentials:
  patient    /app/patient.html#<link token>. The token opens exactly one intake, can only send it,
             never read anything back, and closes when the intake arrives (or after TCM_TOKEN_DAYS).
  clinician  /app/index.html. Signed in with a username and password (session cookie, HttpOnly,
             SameSite=Strict); sees the record list, opens a record, saves the review, the
             diagnostic report and the treatment plan.
"""
import json

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import approvals, sanitize
from .auth import Lockout, check_password
from .config import load_settings
from .crypto import Box
from .store import KINDS, STATUSES, Store

COOKIE = "tcm_session"
MAX_BODY = 2 * 1024 * 1024
CLINICIAN_DOCS = ("review", "report", "plan")


def create_app(settings=None):
    settings = settings or load_settings()
    store = Store(settings.db_path, Box.load(settings.key_dir))
    lockout = Lockout()
    app = FastAPI(title="TCM clinic server", docs_url=None, redoc_url=None, openapi_url=None)
    decisions = approvals.Decisions(store, approvals.load_sign_key(settings.key_dir))
    app.state.store = store
    app.state.decisions = decisions
    app.state.settings = settings

    @app.middleware("http")
    async def guard(request: Request, call_next):
        if request.url.path.startswith("/api/"):
            size = request.headers.get("content-length")
            if size and int(size) > MAX_BODY:
                return JSONResponse({"detail": "too large"}, status_code=413)
            # Clinician writes must come from our own page: a cross-site form cannot set this header.
            if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get("x-tcm") != "1":
                return JSONResponse({"detail": "missing X-TCM header"}, status_code=403)
        response = await call_next(request)
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    async def body(request: Request):
        raw = await request.body()
        if len(raw) > MAX_BODY:
            raise HTTPException(413, "too large")
        try:
            data = json.loads(raw or b"{}")
        except ValueError:
            raise HTTPException(400, "invalid JSON")
        if not isinstance(data, dict):
            raise HTTPException(400, "expected an object")
        return data

    def clinician(request: Request):
        token = request.cookies.get(COOKIE)
        user = token and store.session_user(token)
        if not user:
            raise HTTPException(401, "sign in")
        return "clinician:" + user

    def patient_token(request: Request):
        auth = request.headers.get("authorization", "")
        if not auth.startswith("Bearer ") or len(auth) > 200:
            raise HTTPException(401, "missing link token")
        return auth[7:].strip()

    def record_or_404(rid):
        rec = store.get_record(rid)
        if not rec:
            raise HTTPException(404, "no such record")
        return rec

    @app.get("/api/health")
    def health():
        return {"ok": True, "service": "tcm-clinic-server"}

    # ---- patient side ----
    @app.get("/api/patient/intake")
    def patient_open(token: str = Depends(patient_token)):
        rec = store.record_for_token(token)
        if not rec:
            raise HTTPException(410, "this link is closed or expired")
        return {"open": True, "expires_at": rec["token_expires_at"]}

    @app.post("/api/patient/intake")
    async def patient_submit(request: Request, token: str = Depends(patient_token)):
        data = await body(request)
        try:
            state = sanitize.intake_state(data.get("state"))
        except sanitize.Invalid as e:
            raise HTTPException(422, str(e))
        intake = {"schema_version": "intake.v1", "state": state, "client_created_at": sanitize._text(data.get("created_at"), 40)}
        if not store.submit_intake(token, intake):
            raise HTTPException(410, "this link is closed or expired")
        # Nothing about the record goes back to the patient side, not even its id.
        return {"received": True}

    # ---- clinician sign-in ----
    @app.post("/api/login")
    async def login(request: Request, response: Response):
        data = await body(request)
        user = str(data.get("username", ""))[:64]
        if lockout.locked(user):
            raise HTTPException(429, "too many attempts, try again in a few minutes")
        row = store.clinician(user)
        if not row or not check_password(str(data.get("password", "")), row["pw_hash"]):
            lockout.fail(user)
            raise HTTPException(401, "wrong username or password")
        lockout.ok(user)
        token = store.new_session(user, settings.session_hours)
        response.set_cookie(COOKIE, token, max_age=settings.session_hours * 3600, httponly=True, samesite="strict",
                            secure=settings.force_secure_cookie or request.url.scheme == "https", path="/")
        return {"username": user}

    @app.post("/api/logout")
    def logout(request: Request, response: Response):
        token = request.cookies.get(COOKIE)
        if token:
            store.end_session(token)
        response.delete_cookie(COOKIE, path="/")
        return {"ok": True}

    @app.get("/api/me")
    def me(actor: str = Depends(clinician)):
        return {"username": actor.split(":", 1)[1]}

    # ---- clinician records ----
    def identity_from(data):
        ident = data.get("identity")
        if not ident:
            return None
        if not isinstance(ident, dict):
            raise HTTPException(422, "identity must be an object")
        out = {k: sanitize._text(ident.get(k), 200) for k in ("name", "phone", "note") if ident.get(k)}
        return out or None

    @app.get("/api/records")
    def records(actor: str = Depends(clinician)):
        return {"records": store.list_records()}

    @app.post("/api/records")
    async def new_record(request: Request, actor: str = Depends(clinician)):
        data = await body(request)
        rid, token, expires = store.create_record(actor, settings.token_days, identity_from(data))
        return {"record_id": rid, "patient_token": token, "patient_path": "/app/patient.html#" + token, "expires_at": expires}

    @app.post("/api/records/{rid}/link")
    def new_link(rid: str, actor: str = Depends(clinician)):
        record_or_404(rid)
        try:
            token, expires = store.reissue_token(rid, actor, settings.token_days)
        except ValueError as e:
            raise HTTPException(409, str(e))
        return {"record_id": rid, "patient_token": token, "patient_path": "/app/patient.html#" + token, "expires_at": expires}

    @app.get("/api/records/{rid}")
    def get_record(rid: str, actor: str = Depends(clinician)):
        rec = record_or_404(rid)
        out = {"record_id": rid, "status": rec["status"], "created_at": rec["created_at"], "updated_at": rec["updated_at"],
               "link_expires_at": rec["token_expires_at"], "identity": store.get_identity(rid)}
        for kind in KINDS:
            out[kind] = store.latest(rid, kind)
        out["plan_versions"] = len(store.versions(rid, "plan"))
        with store.db() as c:
            store.audit(c, actor, "open_record", rid)
        return out

    @app.get("/api/records/{rid}/{kind}/versions")
    def doc_versions(rid: str, kind: str, actor: str = Depends(clinician)):
        record_or_404(rid)
        if kind not in KINDS:
            raise HTTPException(404, "unknown kind")
        return {"versions": store.versions(rid, kind)}

    @app.post("/api/records/{rid}/{kind}")
    async def save_doc(rid: str, kind: str, request: Request, actor: str = Depends(clinician)):
        record_or_404(rid)
        if kind not in CLINICIAN_DOCS:
            raise HTTPException(404, "the clinician saves review, report or plan")
        data = await body(request)
        doc = data.get("document")
        if not isinstance(doc, dict):
            raise HTTPException(422, "expected {document: {...}}")
        v = store.put_doc(rid, kind, doc, actor)
        return {"record_id": rid, "kind": kind, "version": v}

    @app.put("/api/records/{rid}/status")
    async def status(rid: str, request: Request, actor: str = Depends(clinician)):
        record_or_404(rid)
        data = await body(request)
        if data.get("status") not in STATUSES:
            raise HTTPException(422, "status must be one of " + ", ".join(STATUSES))
        store.set_status(rid, data["status"], actor)
        return {"record_id": rid, "status": data["status"]}

    @app.put("/api/records/{rid}/identity")
    async def identity(rid: str, request: Request, actor: str = Depends(clinician)):
        record_or_404(rid)
        store.set_identity(rid, identity_from(await body(request)), actor)
        return {"record_id": rid}

    @app.delete("/api/records/{rid}")
    async def delete(rid: str, request: Request, actor: str = Depends(clinician)):
        data = await body(request)
        if data.get("confirm") != rid:
            raise HTTPException(422, "send {confirm: <record id>} to delete")
        if not store.delete_record(rid, actor):
            raise HTTPException(404, "no such record")
        return {"deleted": rid}

    @app.get("/api/records/{rid}/audit")
    def audit(rid: str, actor: str = Depends(clinician)):
        record_or_404(rid)
        return {"audit": store.audit_log(rid)}

    @app.get("/api/export")
    def export(actor: str = Depends(clinician)):
        with store.db() as c:
            store.audit(c, actor, "export")
        return sanitize.export(store)

    # ---- clinical approval of the draft knowledge base (server/approvals.py) ----
    @app.get("/api/kb/decisions")
    def kb_decisions(actor: str = Depends(clinician)):
        rows = decisions.all()
        ok, msg = approvals.verify_chain(rows, decisions.key)
        return {"decisions": list(approvals.effective(rows).values()), "total_rows": len(rows),
                "chain_ok": ok, "chain": msg}

    @app.post("/api/kb/decisions")
    async def kb_decide(request: Request, actor: str = Depends(clinician)):
        data = await body(request)
        batch = data.get("decisions")
        if not isinstance(batch, list) or not batch or len(batch) > 500:
            raise HTTPException(422, "expected {decisions: [...]} with 1 to 500 items")
        try:
            rows = decisions.add(actor, batch)
        except approvals.Invalid as e:
            raise HTTPException(422, str(e))
        return {"saved": rows}

    @app.get("/api/kb/history")
    def kb_history(key: str, actor: str = Depends(clinician)):
        return {"key": key, "rows": decisions.history(key)}

    @app.get("/api/kb/log")
    def kb_log(limit: int = 100, actor: str = Depends(clinician)):
        rows = decisions.all()
        return {"rows": rows[::-1][:max(1, min(limit, 1000))], "total_rows": len(rows)}

    @app.get("/api/kb/export")
    def kb_export(actor: str = Depends(clinician)):
        try:
            out = decisions.export()
        except approvals.Invalid as e:
            raise HTTPException(409, str(e))
        with store.db() as c:
            store.audit(c, actor, "kb_export")
        return JSONResponse(out, headers={"Content-Disposition": 'attachment; filename="decisions.json"'})

    @app.get("/")
    def root():
        return RedirectResponse("/app/index.html")

    app.mount("/app", StaticFiles(directory=settings.app_dir, html=True), name="app")
    return app


def __getattr__(name):
    # `uvicorn server.app:app` builds the app on first use, so importing this module needs no keys.
    if name == "app":
        globals()["app"] = create_app()
        return globals()["app"]
    raise AttributeError(name)
