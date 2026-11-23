"""SQLite storage. Only ids, timestamps and workflow status are in the clear; every clinical
document and every identity field is an AES-GCM blob (see crypto.py).

Tables
  records     record_id (random, e.g. R-7K3QX9MD), status, patient link hash and expiry, timestamps
  documents   append-only versions per record and kind: intake (what the patient sent), review
              (the clinician's working state with tongue and pulse), report (diagnostic_report.v1),
              plan (treatment_plan.v1)
  identities  the optional name/phone/notes for a record, under the separate identity key
  clinicians  username and scrypt password hash
  sessions    sha256 of each clinician session token
  audit       who did what to which record, and when; never any clinical content
"""
import hashlib
import secrets
import sqlite3
import time
from contextlib import contextmanager

SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
  record_id TEXT PRIMARY KEY,
  status TEXT NOT NULL,
  patient_token_hash TEXT UNIQUE,
  token_expires_at INTEGER,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  created_by TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS documents (
  record_id TEXT NOT NULL REFERENCES records(record_id) ON DELETE CASCADE,
  kind TEXT NOT NULL,
  version INTEGER NOT NULL,
  created_at INTEGER NOT NULL,
  created_by TEXT NOT NULL,
  key_id TEXT NOT NULL,
  nonce BLOB NOT NULL,
  ciphertext BLOB NOT NULL,
  PRIMARY KEY (record_id, kind, version)
);
CREATE TABLE IF NOT EXISTS identities (
  record_id TEXT PRIMARY KEY REFERENCES records(record_id) ON DELETE CASCADE,
  key_id TEXT NOT NULL,
  nonce BLOB NOT NULL,
  ciphertext BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS clinicians (
  username TEXT PRIMARY KEY,
  pw_hash TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1,
  created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
  token_hash TEXT PRIMARY KEY,
  username TEXT NOT NULL REFERENCES clinicians(username) ON DELETE CASCADE,
  expires_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  at INTEGER NOT NULL,
  actor TEXT NOT NULL,
  action TEXT NOT NULL,
  record_id TEXT
);
"""

STATUSES = ("awaiting_patient", "submitted", "in_review", "closed")
KINDS = ("intake", "review", "report", "plan")
# Crockford base32 without I, L, O, U: easy to read out and to type.
_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def now():
    return int(time.time())


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def new_record_id():
    return "R-" + "".join(secrets.choice(_ALPHABET) for _ in range(8))


def _aad(record_id, kind, version):
    return f"{record_id}|{kind}|{version}"


class Store:
    def __init__(self, db_path, box):
        self.db_path = db_path
        self.box = box
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.db() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def db(self):
        c = sqlite3.connect(self.db_path, timeout=10)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys = ON")
        c.execute("PRAGMA journal_mode = WAL")
        c.execute("PRAGMA secure_delete = ON")   # deleted rows are overwritten, not left in free pages
        try:
            yield c
            c.commit()
        finally:
            c.close()

    def audit(self, c, actor, action, record_id=None):
        c.execute("INSERT INTO audit (at, actor, action, record_id) VALUES (?, ?, ?, ?)", (now(), actor, action, record_id))

    # ---- records ----
    def create_record(self, actor, token_days, identity=None):
        token = secrets.token_urlsafe(24)
        expires = now() + token_days * 86400
        with self.db() as c:
            for _ in range(10):
                rid = new_record_id()
                try:
                    c.execute("INSERT INTO records VALUES (?, 'awaiting_patient', ?, ?, ?, ?, ?)",
                              (rid, sha256(token), expires, now(), now(), actor))
                    break
                except sqlite3.IntegrityError:
                    continue
            else:
                raise RuntimeError("could not allocate a record id")
            if identity:
                self._put_identity(c, rid, identity)
            self.audit(c, actor, "create_record", rid)
        return rid, token, expires

    def reissue_token(self, rid, actor, token_days):
        token = secrets.token_urlsafe(24)
        expires = now() + token_days * 86400
        with self.db() as c:
            row = c.execute("SELECT status FROM records WHERE record_id = ?", (rid,)).fetchone()
            if not row:
                return None
            if row["status"] != "awaiting_patient":
                raise ValueError("the patient already submitted this intake")
            c.execute("UPDATE records SET patient_token_hash = ?, token_expires_at = ?, updated_at = ? WHERE record_id = ?",
                      (sha256(token), expires, now(), rid))
            self.audit(c, actor, "reissue_link", rid)
        return token, expires

    def record_for_token(self, token):
        with self.db() as c:
            row = c.execute("SELECT * FROM records WHERE patient_token_hash = ?", (sha256(token),)).fetchone()
        if not row or row["status"] != "awaiting_patient" or row["token_expires_at"] < now():
            return None
        return dict(row)

    def submit_intake(self, token, intake):
        """Store the patient's intake and close the link, in one transaction."""
        with self.db() as c:
            row = c.execute("SELECT * FROM records WHERE patient_token_hash = ?", (sha256(token),)).fetchone()
            if not row or row["status"] != "awaiting_patient" or row["token_expires_at"] < now():
                return None
            rid = row["record_id"]
            self._put_doc(c, rid, "intake", intake, "patient")
            c.execute("UPDATE records SET status = 'submitted', patient_token_hash = NULL, token_expires_at = NULL, updated_at = ? WHERE record_id = ?",
                      (now(), rid))
            self.audit(c, "patient", "submit_intake", rid)
        return rid

    def get_record(self, rid):
        with self.db() as c:
            row = c.execute("SELECT * FROM records WHERE record_id = ?", (rid,)).fetchone()
        return dict(row) if row else None

    def list_records(self):
        with self.db() as c:
            rows = [dict(r) for r in c.execute("SELECT * FROM records ORDER BY updated_at DESC")]
            ids = {r["record_id"]: self._get_identity(c, r["record_id"]) for r in rows}
            intakes = {r["record_id"]: self._latest(c, r["record_id"], "intake") for r in rows}
            counts = {}
            for d in c.execute("SELECT record_id, kind, COUNT(*) AS n FROM documents GROUP BY record_id, kind"):
                counts.setdefault(d["record_id"], {})[d["kind"]] = d["n"]
        out = []
        for r in rows:
            intake = (intakes[r["record_id"]] or {}).get("data") or {}
            state = intake.get("state") or {}
            patient = state.get("patient") or {}
            out.append({
                "record_id": r["record_id"], "status": r["status"],
                "created_at": r["created_at"], "updated_at": r["updated_at"],
                "link_expires_at": r["token_expires_at"],
                "identity": ids[r["record_id"]],
                "age": patient.get("age"), "sex": patient.get("sex"),
                "halted": bool(state.get("halted")),
                "documents": counts.get(r["record_id"], {}),
            })
        return out

    def set_status(self, rid, status, actor):
        if status not in STATUSES:
            raise ValueError("unknown status")
        with self.db() as c:
            n = c.execute("UPDATE records SET status = ?, updated_at = ? WHERE record_id = ?", (status, now(), rid)).rowcount
            if n:
                self.audit(c, actor, "status:" + status, rid)
        return bool(n)

    def delete_record(self, rid, actor):
        with self.db() as c:
            n = c.execute("DELETE FROM records WHERE record_id = ?", (rid,)).rowcount
            if n:
                self.audit(c, actor, "delete_record", rid)
        return bool(n)

    # ---- documents ----
    def _put_doc(self, c, rid, kind, data, actor):
        if kind not in KINDS:
            raise ValueError("unknown document kind")
        v = c.execute("SELECT COALESCE(MAX(version), 0) + 1 FROM documents WHERE record_id = ? AND kind = ?", (rid, kind)).fetchone()[0]
        kid, nonce, blob = self.box.seal("data", data, _aad(rid, kind, v))
        c.execute("INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (rid, kind, v, now(), actor, kid, nonce, blob))
        return v

    def put_doc(self, rid, kind, data, actor):
        with self.db() as c:
            v = self._put_doc(c, rid, kind, data, actor)
            c.execute("UPDATE records SET updated_at = ?, status = CASE WHEN status = 'submitted' THEN 'in_review' ELSE status END WHERE record_id = ?",
                      (now(), rid))
            self.audit(c, actor, f"save:{kind}:v{v}", rid)
        return v

    def _open_doc(self, rid, row):
        return {"version": row["version"], "created_at": row["created_at"], "created_by": row["created_by"],
                "data": self.box.open("data", row["key_id"], row["nonce"], row["ciphertext"], _aad(rid, row["kind"], row["version"]))}

    def _latest(self, c, rid, kind):
        row = c.execute("SELECT * FROM documents WHERE record_id = ? AND kind = ? ORDER BY version DESC LIMIT 1", (rid, kind)).fetchone()
        return self._open_doc(rid, row) if row else None

    def latest(self, rid, kind):
        with self.db() as c:
            return self._latest(c, rid, kind)

    def versions(self, rid, kind):
        with self.db() as c:
            return [self._open_doc(rid, r) for r in c.execute(
                "SELECT * FROM documents WHERE record_id = ? AND kind = ? ORDER BY version", (rid, kind))]

    def all_docs(self):
        with self.db() as c:
            return [(r["record_id"], r["kind"], self._open_doc(r["record_id"], r)) for r in c.execute(
                "SELECT * FROM documents ORDER BY record_id, kind, version")]

    # ---- identity ----
    def _put_identity(self, c, rid, identity):
        kid, nonce, blob = self.box.seal("identity", identity, _aad(rid, "identity", 0))
        c.execute("INSERT OR REPLACE INTO identities VALUES (?, ?, ?, ?)", (rid, kid, nonce, blob))

    def _get_identity(self, c, rid):
        row = c.execute("SELECT * FROM identities WHERE record_id = ?", (rid,)).fetchone()
        return self.box.open("identity", row["key_id"], row["nonce"], row["ciphertext"], _aad(rid, "identity", 0)) if row else None

    def get_identity(self, rid):
        with self.db() as c:
            return self._get_identity(c, rid)

    def set_identity(self, rid, identity, actor):
        with self.db() as c:
            if identity:
                self._put_identity(c, rid, identity)
            else:
                c.execute("DELETE FROM identities WHERE record_id = ?", (rid,))
            self.audit(c, actor, "set_identity", rid)

    # ---- clinicians and sessions ----
    def add_clinician(self, username, pw_hash):
        with self.db() as c:
            c.execute("INSERT INTO clinicians (username, pw_hash, created_at) VALUES (?, ?, ?) "
                      "ON CONFLICT(username) DO UPDATE SET pw_hash = excluded.pw_hash, active = 1", (username, pw_hash, now()))
            c.execute("DELETE FROM sessions WHERE username = ?", (username,))
            self.audit(c, "admin", "set_clinician:" + username)

    def deactivate_clinician(self, username):
        with self.db() as c:
            n = c.execute("UPDATE clinicians SET active = 0 WHERE username = ?", (username,)).rowcount
            c.execute("DELETE FROM sessions WHERE username = ?", (username,))
            self.audit(c, "admin", "deactivate_clinician:" + username)
        return bool(n)

    def clinician(self, username):
        with self.db() as c:
            row = c.execute("SELECT * FROM clinicians WHERE username = ? AND active = 1", (username,)).fetchone()
        return dict(row) if row else None

    def new_session(self, username, hours):
        token = secrets.token_urlsafe(32)
        with self.db() as c:
            c.execute("DELETE FROM sessions WHERE expires_at < ?", (now(),))
            c.execute("INSERT INTO sessions VALUES (?, ?, ?)", (sha256(token), username, now() + hours * 3600))
            self.audit(c, "clinician:" + username, "login")
        return token

    def session_user(self, token):
        with self.db() as c:
            row = c.execute("SELECT s.username FROM sessions s JOIN clinicians k ON k.username = s.username "
                            "WHERE s.token_hash = ? AND s.expires_at >= ? AND k.active = 1", (sha256(token), now())).fetchone()
        return row["username"] if row else None

    def end_session(self, token):
        with self.db() as c:
            c.execute("DELETE FROM sessions WHERE token_hash = ?", (sha256(token),))

    def audit_log(self, rid=None, limit=200):
        with self.db() as c:
            q = "SELECT at, actor, action, record_id FROM audit" + (" WHERE record_id = ?" if rid else "") + " ORDER BY id DESC LIMIT ?"
            return [dict(r) for r in c.execute(q, ((rid, limit) if rid else (limit,)))]
