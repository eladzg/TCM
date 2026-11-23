"""Clinical approval of the draft KB: the signed decision log (server/approvals.py), its API, and the
builds laying the exported decisions over the draft."""
import json

import pytest

from server import approvals

pytest.importorskip("fastapi")
pytest.importorskip("cryptography")
from fastapi.testclient import TestClient  # noqa: E402

from server.app import create_app  # noqa: E402
from server.auth import hash_password  # noqa: E402
from server.config import load_settings  # noqa: E402
from server.crypto import create_keys  # noqa: E402

H = {"X-TCM": "1"}
PW = "correct horse battery"


@pytest.fixture()
def client(tmp_path):
    s = load_settings(data_dir=tmp_path, key_dir=tmp_path / "keys")
    create_keys(s.key_dir)
    app = create_app(s)
    app.state.store.add_clinician("dana", hash_password(PW))
    c = TestClient(app)
    assert c.post("/api/login", json={"username": "dana", "password": PW}, headers=H).status_code == 200
    return c, app


def test_needs_sign_in_and_header(tmp_path):
    s = load_settings(data_dir=tmp_path, key_dir=tmp_path / "keys")
    create_keys(s.key_dir)
    c = TestClient(create_app(s))
    assert c.get("/api/kb/decisions").status_code == 401
    assert c.post("/api/kb/decisions", json={"decisions": []}).status_code == 403


def test_decisions_are_signed_chained_and_latest_wins(client):
    c, app = client
    batch = [
        {"key": "link:SYN.A|FT.HEADACHE", "action": "edit", "value": {"w": 2.5}, "draft": {"w": 1.0, "src": ["WHO"]}},
        {"key": "pattern:SYN.B", "action": "reject", "note": "too narrow"},
        {"key": "tx:SYN.A|point|LR3", "action": "approve", "draft": {"s": 4.2}},
    ]
    r = c.post("/api/kb/decisions", json={"decisions": batch}, headers=H)
    assert r.status_code == 200, r.text
    rows = r.json()["saved"]
    assert [x["seq"] for x in rows] == [1, 2, 3]
    assert rows[0]["actor"] == "clinician:dana" and rows[1]["prev"] == rows[0]["hash"]
    c.post("/api/kb/decisions", json={"decisions": [{"key": "pattern:SYN.B", "action": "reset"}]}, headers=H)
    got = c.get("/api/kb/decisions").json()
    assert got["chain_ok"] and got["total_rows"] == 4
    keys = {d["key"]: d for d in got["decisions"]}
    assert "pattern:SYN.B" not in keys and keys["link:SYN.A|FT.HEADACHE"]["value"] == {"w": 2.5}
    assert len(c.get("/api/kb/history", params={"key": "pattern:SYN.B"}).json()["rows"]) == 2
    exp = c.get("/api/kb/export").json()
    assert exp["schema_version"] == "kb_decisions.v1" and exp["head"] == exp["rows"][-1]["hash"]
    assert approvals.verify_chain(exp["rows"])[0]


@pytest.mark.parametrize("bad", [
    {"key": "link:SYN.A|FT.X", "action": "edit", "value": {"w": 9}},
    {"key": "link:SYN.A|FT.X", "action": "edit", "value": {"w": "2"}},
    {"key": "safety:SAFE.X", "action": "reject"},                    # safety rules cannot be switched off
    {"key": "safety:SAFE.X", "action": "dispute"},                   # a dispute needs a note
    {"key": "tx:SYN.A|method|2283", "action": "add"},
    {"key": "drop table", "action": "approve"},
    {"key": "feature:FT.X", "action": "edit", "value": {}},
])
def test_invalid_decisions_are_refused_whole(client, bad):
    c, _ = client
    ok = {"key": "pattern:SYN.A", "action": "approve"}
    r = c.post("/api/kb/decisions", json={"decisions": [ok, bad]}, headers=H)
    assert r.status_code == 422
    assert c.get("/api/kb/decisions").json()["total_rows"] == 0


def test_tampering_is_detected(client):
    c, app = client
    c.post("/api/kb/decisions", json={"decisions": [{"key": "link:SYN.A|FT.X", "action": "edit", "value": {"w": 2}},
                                                    {"key": "pattern:SYN.A", "action": "approve"}]}, headers=H)
    with app.state.store.db() as db:
        db.execute("UPDATE kb_decisions SET value = ? WHERE seq = 1", (json.dumps({"w": 3}),))
    got = c.get("/api/kb/decisions").json()
    assert not got["chain_ok"] and "row 1" in got["chain"]
    assert c.get("/api/kb/export").status_code == 409


def test_signature_needs_the_server_key(client):
    c, app = client
    c.post("/api/kb/decisions", json={"decisions": [{"key": "pattern:SYN.A", "action": "approve"}]}, headers=H)
    rows = app.state.decisions.all()
    assert approvals.verify_chain(rows, app.state.decisions.key)[0]
    assert not approvals.verify_chain(rows, b"x" * 32)[0]


# ---- the builds ----

def _export(rows_in, path):
    rows, prev = [], approvals.GENESIS
    for i, d in enumerate(rows_in, 1):
        row = {"seq": i, "at": 1700000000 + i, "actor": "clinician:dana", "value": None, "draft": None, "note": "", **d, "prev": prev}
        row["hash"] = approvals.row_hash(row)
        row["sig"] = ""
        rows.append(row)
        prev = row["hash"]
    path.write_text(json.dumps({"schema_version": "kb_decisions.v1", "head": prev, "rows": rows}), encoding="utf-8")


def test_builds_apply_decisions(tmp_path, monkeypatch):
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "tools" / "interview"))
    sys.path.insert(0, str(root / "tools" / "treatment"))
    import build_interview as bi
    base = bi.build_data()
    syn = next(s for s in base["syndromes"] if len(s["links"]) >= 3 and "prior" not in s)
    sid, l0, l1 = syn["id"], syn["links"][0], syn["links"][1]
    linked = {l["f"] for l in syn["links"]}
    new_f = next(f["id"] for f in base["features"] if f["id"] not in linked)
    other = next(s["id"] for s in base["syndromes"] if s["id"] != sid)
    path = tmp_path / "decisions.json"
    _export([
        {"key": f"link:{sid}|{l0['f']}", "action": "edit", "value": {"w": 3.0}, "draft": {"w": 99, "src": l0["src"]}},
        {"key": f"link:{sid}|{l1['f']}", "action": "reject"},
        {"key": f"link:{sid}|{new_f}", "action": "edit", "value": {"w": 2.0}},
        {"key": f"pattern:{other}", "action": "reject"},
        {"key": f"pattern:{sid}", "action": "approve"},
        {"key": "feature:" + l0["f"], "action": "edit", "value": {"label_he": "תווית מאושרת"}},
        {"key": "link:SYN.NOPE|FT.NOPE", "action": "approve"},
    ], path)
    monkeypatch.setattr(bi, "DECISIONS", path)
    data = bi.build_data()
    s = next(x for x in data["syndromes"] if x["id"] == sid)
    by_f = {l["f"]: l for l in s["links"]}
    assert by_f[l0["f"]]["w"] == 3.0 and "dw" in by_f[l0["f"]] and by_f[l0["f"]]["ok"]["by"] == "dana"
    assert l1["f"] not in by_f and s["rej"][0]["f"] == l1["f"]
    assert by_f[new_f]["src"] == ["clinician"] and by_f[new_f]["w"] == 2.0
    assert s["status"] == "approved"
    assert next(x for x in data["syndromes"] if x["id"] == other)["status"] == "rejected"
    assert next(f for f in data["features"] if f["id"] == l0["f"])["label_he"] == "תווית מאושרת"
    a = data["approvals"]
    assert a["applied"] == 6 and a["orphans"] == ["link:SYN.NOPE|FT.NOPE"]
    assert a["changed"] == [f"link:{sid}|{l0['f']}"] and a["head_seq"] == 7

    # a changed row stops the build
    raw = json.loads(path.read_text())
    raw["rows"][0]["value"] = {"w": 5.0}
    path.write_text(json.dumps(raw))
    with pytest.raises(SystemExit):
        bi.build_data()


def test_treatment_build_applies_decisions(tmp_path, monkeypatch):
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "tools" / "interview"))
    sys.path.insert(0, str(root / "tools" / "treatment"))
    pytest.importorskip("opencc")
    import build_interview as bi
    import build_treatment as bt
    base = bt.build_data()
    sid = next(k for k, v in base["links"].items() if len(v["p"]) >= 2 and v["fm"])
    p0, p1 = base["links"][sid]["p"][0]["id"], base["links"][sid]["p"][1]["id"]
    have = {p["id"] for p in base["links"][sid]["p"]}
    extra = next(k for k in base["points"] if k not in have)
    rule = base["safety"][0]["id"]
    path = tmp_path / "decisions.json"
    _export([
        {"key": f"tx:{sid}|point|{p0}", "action": "reject"},
        {"key": f"tx:{sid}|point|{p1}", "action": "approve"},
        {"key": f"tx:{sid}|point|{extra}", "action": "add"},
        {"key": f"safety:{rule}", "action": "dispute", "note": "only in large doses"},
    ], path)
    monkeypatch.setattr(bi, "DECISIONS", path)
    data = bt.build_data()
    pts = data["links"][sid]["p"]
    ids = [p["id"] for p in pts]
    assert p0 not in ids and {"t": "point", "id": p0} == {k: data["links"][sid]["x"][0][k] for k in ("t", "id")}
    assert ids[0] == extra and pts[0]["add"] == 1
    assert next(p for p in pts if p["id"] == p1)["ok"]["by"] == "dana"
    r = next(x for x in data["safety"] if x["id"] == rule)
    assert r["disputed"]["note"] == "only in large doses" and r["status"] != "approved"   # still fires
    assert data["approvals"]["applied"] == 4
