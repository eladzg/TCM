"""Clinic server: encrypted storage, the patient link, the clinician side, the export."""
import sqlite3

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("cryptography")
from fastapi.testclient import TestClient  # noqa: E402

from server import sanitize  # noqa: E402
from server.app import create_app  # noqa: E402
from server.auth import hash_password  # noqa: E402
from server.config import load_settings  # noqa: E402
from server.crypto import Box, create_keys  # noqa: E402

H = {"X-TCM": "1"}
PW = "correct horse battery"

STATE = {
    "patient": {"age": 47, "sex": "F", "pregnancy": "no", "medications": "קומדין"},
    "answers": {
        "headache": {"value": True, "source": "free_text", "quote": "כואב לי הראש, אני דנה כהן"},
        "insomnia": {"value": False, "source": "question", "quote": ""},
        "tongue_red": {"value": True, "source": "clinician", "quote": ""},   # the patient cannot set this
    },
    "asked": ["insomnia"], "adaptiveAsked": 0, "flags": [], "halted": False,
    "tongueObserved": True, "pulseObserved": True,
    "transcript": [{"role": "patient", "text": "כואב לי הראש, אני דנה כהן", "context": "chief_complaint"}],
    "evil": "<script>",
}


@pytest.fixture()
def env(tmp_path):
    s = load_settings(data_dir=tmp_path, key_dir=tmp_path / "keys")
    create_keys(s.key_dir)
    app = create_app(s)
    app.state.store.add_clinician("dana", hash_password(PW))
    return app, s


def signed_in(app):
    c = TestClient(app)
    r = c.post("/api/login", json={"username": "dana", "password": PW}, headers=H)
    assert r.status_code == 200
    return c


def new_record(c, identity=None):
    r = c.post("/api/records", json={"identity": identity}, headers=H)
    assert r.status_code == 200
    return r.json()


def test_health_and_static(env):
    app, _ = env
    c = TestClient(app)
    assert c.get("/api/health").json()["service"] == "tcm-clinic-server"
    assert c.get("/app/patient.html").status_code == 200
    assert "records.js" in c.get("/app/index.html").text


def test_clinician_api_needs_sign_in(env):
    app, _ = env
    c = TestClient(app)
    assert c.get("/api/records").status_code == 401
    assert c.post("/api/records", json={}, headers=H).status_code == 401
    assert c.post("/api/login", json={"username": "dana", "password": "wrong password"}, headers=H).status_code == 401


def test_writes_need_the_header(env):
    app, _ = env
    c = signed_in(app)
    assert c.post("/api/records", json={}).status_code == 403


def test_lockout(env):
    app, _ = env
    c = TestClient(app)
    for _ in range(5):
        c.post("/api/login", json={"username": "dana", "password": "nope nope nope"}, headers=H)
    assert c.post("/api/login", json={"username": "dana", "password": PW}, headers=H).status_code == 429


def test_patient_link_round_trip(env):
    app, _ = env
    c = signed_in(app)
    rec = new_record(c, {"name": "דנה כהן", "phone": "050-0000000"})
    rid, token = rec["record_id"], rec["patient_token"]
    assert rid.startswith("R-") and len(rid) == 10
    assert rec["patient_path"].endswith("#" + token)

    p = TestClient(app)   # no clinician cookie
    auth = {"Authorization": "Bearer " + token, **H}
    assert p.get("/api/patient/intake", headers=auth).json()["open"] is True
    r = p.post("/api/patient/intake", json={"state": STATE}, headers=auth)
    assert r.status_code == 200 and r.json() == {"received": True}
    # one use only; and the token never reads anything back
    assert p.get("/api/patient/intake", headers=auth).status_code == 410
    assert p.post("/api/patient/intake", json={"state": STATE}, headers=auth).status_code == 410
    assert p.get("/api/records/" + rid, headers=auth).status_code == 401

    got = c.get("/api/records/" + rid).json()
    assert got["status"] == "submitted"
    assert got["identity"]["name"] == "דנה כהן"
    st = got["intake"]["data"]["state"]
    assert "tongue_red" not in st["answers"] and "evil" not in st
    assert st["tongueObserved"] is False
    assert st["answers"]["headache"]["value"] is True

    listed = c.get("/api/records").json()["records"]
    assert listed[0]["record_id"] == rid and listed[0]["age"] == 47


def test_bad_or_missing_token(env):
    app, _ = env
    p = TestClient(app)
    assert p.get("/api/patient/intake").status_code == 401
    assert p.post("/api/patient/intake", json={"state": STATE}, headers={"Authorization": "Bearer nope", **H}).status_code == 410


def test_reissued_link_closes_the_old_one(env):
    app, _ = env
    c = signed_in(app)
    rec = new_record(c)
    new = c.post("/api/records/%s/link" % rec["record_id"], headers=H).json()
    p = TestClient(app)
    assert p.get("/api/patient/intake", headers={"Authorization": "Bearer " + rec["patient_token"]}).status_code == 410
    assert p.get("/api/patient/intake", headers={"Authorization": "Bearer " + new["patient_token"]}).status_code == 200


def test_expired_link(env):
    app, s = env
    c = signed_in(app)
    rec = new_record(c)
    with sqlite3.connect(s.db_path) as db:
        db.execute("UPDATE records SET token_expires_at = 1")
    p = TestClient(app)
    assert p.get("/api/patient/intake", headers={"Authorization": "Bearer " + rec["patient_token"]}).status_code == 410


def test_clinician_documents_are_versioned(env):
    app, _ = env
    c = signed_in(app)
    rid = new_record(c)["record_id"]
    for i in range(2):
        r = c.post("/api/records/%s/plan" % rid, json={"document": {"schema_version": "treatment_plan.v1", "n": i}}, headers=H)
        assert r.json()["version"] == i + 1
    assert c.post("/api/records/%s/intake" % rid, json={"document": {}}, headers=H).status_code == 404
    got = c.get("/api/records/" + rid).json()
    assert got["plan"]["data"]["n"] == 1 and got["plan_versions"] == 2
    assert [v["data"]["n"] for v in c.get("/api/records/%s/plan/versions" % rid).json()["versions"]] == [0, 1]
    actions = [a["action"] for a in c.get("/api/records/%s/audit" % rid).json()["audit"]]
    assert "save:plan:v2" in actions and "create_record" in actions


def test_nothing_clinical_in_the_clear(env):
    app, s = env
    c = signed_in(app)
    rec = new_record(c, {"name": "דנה כהן"})
    TestClient(app).post("/api/patient/intake", json={"state": STATE}, headers={"Authorization": "Bearer " + rec["patient_token"], **H})
    raw = s.db_path.read_bytes()
    for wal in s.db_path.parent.glob("records.db-*"):
        raw += wal.read_bytes()
    for secret in ("דנה כהן", "קומדין", "headache", rec["patient_token"]):
        assert secret.encode("utf-8") not in raw


def test_blob_bound_to_its_row(env):
    app, s = env
    c = signed_in(app)
    a = new_record(c)["record_id"]
    b = new_record(c)["record_id"]
    c.post("/api/records/%s/plan" % a, json={"document": {"who": "a"}}, headers=H)
    c.post("/api/records/%s/plan" % b, json={"document": {"who": "b"}}, headers=H)
    with sqlite3.connect(s.db_path) as db:
        blob_a = db.execute("SELECT nonce, ciphertext FROM documents WHERE record_id = ?", (a,)).fetchone()
        db.execute("UPDATE documents SET nonce = ?, ciphertext = ? WHERE record_id = ?", (blob_a[0], blob_a[1], b))
    with pytest.raises(Exception):
        app.state.store.latest(b, "plan")


def test_wrong_key_cannot_read(env, tmp_path):
    app, s = env
    c = signed_in(app)
    rid = new_record(c)["record_id"]
    c.post("/api/records/%s/plan" % rid, json={"document": {"x": 1}}, headers=H)
    other = tmp_path / "other"
    create_keys(other)
    from server.store import Store
    with pytest.raises(Exception):
        Store(s.db_path, Box.load(other)).latest(rid, "plan")


def test_delete_needs_confirmation(env):
    app, _ = env
    c = signed_in(app)
    rid = new_record(c)["record_id"]
    assert c.request("DELETE", "/api/records/" + rid, json={}, headers=H).status_code == 422
    assert c.request("DELETE", "/api/records/" + rid, json={"confirm": rid}, headers=H).status_code == 200
    assert c.get("/api/records/" + rid).status_code == 404


def test_export_is_deidentified(env):
    app, _ = env
    c = signed_in(app)
    rec = new_record(c, {"name": "דנה כהן"})
    rid = rec["record_id"]
    TestClient(app).post("/api/patient/intake", json={"state": STATE}, headers={"Authorization": "Bearer " + rec["patient_token"], **H})
    c.post("/api/records/%s/plan" % rid, json={"document": {"clinician_note_he": "דנה מגיעה ביום ג", "acupuncture": [{"point_id": "LR3", "note_he": "x"}]}}, headers=H)
    out = c.get("/api/export").json()
    text = str(out)
    assert "דנה" not in text and "קומדין" not in text and rid not in text
    recs = out["records"]
    assert len(recs) == 1
    assert recs[0]["intake"][0]["data"]["state"]["patient"]["age_band"] == "40-49"
    assert recs[0]["plan"][0]["data"]["acupuncture"] == [{"point_id": "LR3"}]


def test_sanitize_rejects_bad_input():
    with pytest.raises(sanitize.Invalid):
        sanitize.intake_state({"patient": {"age": 500}})
    with pytest.raises(sanitize.Invalid):
        sanitize.intake_state({"answers": {"../x": {"value": True, "source": "question"}}})
    with pytest.raises(sanitize.Invalid):
        sanitize.intake_state("nope")
