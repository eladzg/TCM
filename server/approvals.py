"""Clinician decisions on the draft knowledge base: approve, edit a weight, reject, or add.

Every row the builds derive (a pattern, a pattern-finding link and its weight, a lexicon finding's
wording, a pattern's suggested point / herb / formula / WHO method, a safety rule) is a DRAFT. The
clinician reviews it in the "אישור קליני" tab and each decision becomes one row of an append-only,
hash-chained log:

  seq, at, actor, key, action, value, draft, note, prev, hash, sig

  key     what the decision is about, e.g. "link:SYN.LIVER.YANG_HYPER|FT.HEADACHE" (see KEY_FORMS)
  action  approve | edit | reject | add | dispute | reset   (reset returns the item to draft)
  value   the clinician's value: {"w": 2.0} for a link weight, {"q_he": ..., "label_he": ...} for wording
  draft   the draft the clinician saw when deciding (for the record: the source data is never changed)
  hash    sha256 of the row's fields and the previous row's hash, so an edited or deleted row breaks the chain
  sig     HMAC-SHA256 of the hash under the server's sign.key: only this server could have written the row

Nothing here edits kb/ source files. The log is exported to kb/approvals/decisions.json
(`python -m server.manage kb-export`, or the export button in the tab), and the builds
(tools/interview/build_interview.py, tools/treatment/build_treatment.py) lay the latest decision per
key over the draft. This module needs only the standard library, so the builds can import it.

Safety rules cannot be switched off from here: a clinician who disagrees with one marks it "dispute"
with a note, and the rule keeps firing (modern safety warnings take precedence over the review).
"""
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS kb_decisions (
  seq INTEGER PRIMARY KEY,
  at INTEGER NOT NULL,
  actor TEXT NOT NULL,
  key TEXT NOT NULL,
  action TEXT NOT NULL,
  value TEXT,
  draft TEXT,
  note TEXT NOT NULL DEFAULT '',
  prev TEXT NOT NULL,
  hash TEXT NOT NULL UNIQUE,
  sig TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS kb_decisions_key ON kb_decisions(key);
"""

GENESIS = "0" * 64
ID = r"[A-Z0-9][A-Za-z0-9_.\-]{0,80}"
KEY_FORMS = {
    "pattern": re.compile(rf"^pattern:({ID})$"),
    "link": re.compile(rf"^link:({ID})\|({ID})$"),
    "feature": re.compile(rf"^feature:({ID})$"),
    "tx": re.compile(rf"^tx:({ID})\|(point|herb|formula|method)\|({ID}|\d{{1,6}})$"),
    "safety": re.compile(rf"^safety:({ID})$"),
}
ACTIONS = {
    "pattern": {"approve", "reject", "reset"},
    "link": {"approve", "edit", "reject", "reset"},     # "edit" on a link the draft lacks adds it
    "feature": {"approve", "edit", "reset"},
    "tx": {"approve", "reject", "add", "reset"},
    "safety": {"approve", "dispute", "reset"},
}
W_MIN, W_MAX = 0.1, 5.0
TEXT_MAX = 400


class Invalid(ValueError):
    pass


def key_type(key):
    for kind, rx in KEY_FORMS.items():
        if rx.match(key):
            return kind
    return None


def _clean_text(v, limit=TEXT_MAX):
    if v is None:
        return ""
    if not isinstance(v, str):
        raise Invalid("text expected")
    v = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", v).strip()
    if len(v) > limit:
        raise Invalid(f"text longer than {limit} characters")
    return v


def _small_json(v, limit=2000):
    """The draft snapshot: a small JSON object of plain values, kept for the record."""
    if v is None:
        return None
    if not isinstance(v, dict):
        raise Invalid("draft must be an object")
    text = json.dumps(v, ensure_ascii=False, sort_keys=True)
    if len(text) > limit:
        raise Invalid("draft snapshot too large")
    return json.loads(text)


def validate(d):
    """One decision from the client -> {key, action, value, draft, note}, or Invalid."""
    if not isinstance(d, dict):
        raise Invalid("each decision must be an object")
    key = d.get("key")
    if not isinstance(key, str) or len(key) > 200:
        raise Invalid("key expected")
    kind = key_type(key)
    if not kind:
        raise Invalid(f"unknown key form: {key}")
    action = d.get("action")
    if action not in ACTIONS[kind]:
        raise Invalid(f"{kind}: action must be one of {', '.join(sorted(ACTIONS[kind]))}")
    note = _clean_text(d.get("note"))
    value = None
    raw = d.get("value") or {}
    if not isinstance(raw, dict):
        raise Invalid("value must be an object")
    if kind == "link" and action == "edit":
        w = raw.get("w")
        if isinstance(w, bool) or not isinstance(w, (int, float)) or not (W_MIN <= float(w) <= W_MAX):
            raise Invalid(f"weight must be a number from {W_MIN} to {W_MAX}")
        value = {"w": round(float(w), 2)}
    elif kind == "feature" and action == "edit":
        value = {k: _clean_text(raw.get(k), 300) for k in ("q_he", "label_he") if raw.get(k)}
        if not value:
            raise Invalid("edit needs q_he or label_he")
    if action in ("dispute",) and not note:
        raise Invalid("a disputed safety rule needs a note saying why")
    if kind == "tx" and action == "add" and key.split("|")[1] == "method":
        raise Invalid("WHO methods come from the WHO text; approve or reject them")
    return {"key": key, "action": action, "value": value, "draft": _small_json(d.get("draft")), "note": note}


def row_hash(row):
    body = {k: row[k] for k in ("seq", "at", "actor", "key", "action", "value", "draft", "note", "prev")}
    text = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def verify_chain(rows, sign_key=None):
    """(ok, message). Checks order, links and hashes; with the key, the signatures too."""
    prev = GENESIS
    for i, r in enumerate(rows):
        if r["prev"] != prev:
            return False, f"row {r.get('seq')}: chain broken (a row before it was changed or removed)"
        if row_hash(r) != r["hash"]:
            return False, f"row {r.get('seq')}: content does not match its hash"
        if sign_key is not None and not hmac.compare_digest(sign(sign_key, r["hash"]), r.get("sig", "")):
            return False, f"row {r.get('seq')}: signature not made by this server"
        prev = r["hash"]
    return True, f"{len(rows)} decisions, chain intact"


def sign(key: bytes, digest: str) -> str:
    return hmac.new(key, digest.encode("ascii"), hashlib.sha256).hexdigest()


def load_sign_key(key_dir: Path, create=True) -> bytes:
    env = os.environ.get("TCM_SIGN_KEY")
    if env:
        return base64.b64decode(env.strip())
    path = Path(key_dir) / "sign.key"
    if not path.exists():
        if not create:
            raise FileNotFoundError(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(base64.b64encode(secrets.token_bytes(32)).decode("ascii") + "\n")
    return base64.b64decode(path.read_text().strip())


def effective(rows):
    """The latest decision per key; a reset removes the key (back to draft)."""
    out = {}
    for r in rows:
        if r["action"] == "reset":
            out.pop(r["key"], None)
        else:
            out[r["key"]] = r
    return out


class Decisions:
    """The log inside the clinic server's SQLite file (store.Store.db)."""

    def __init__(self, store, sign_key: bytes):
        self.store = store
        self.key = sign_key
        with store.db() as c:
            c.executescript(SCHEMA)

    @staticmethod
    def _row(r):
        d = dict(r)
        d["value"] = json.loads(d["value"]) if d["value"] else None
        d["draft"] = json.loads(d["draft"]) if d["draft"] else None
        return d

    def add(self, actor, decisions):
        """Append a batch in one transaction; returns the new rows."""
        clean = [validate(d) for d in decisions]
        out = []
        with self.store.db() as c:
            c.execute("BEGIN IMMEDIATE")
            last = c.execute("SELECT seq, hash FROM kb_decisions ORDER BY seq DESC LIMIT 1").fetchone()
            seq, prev = (last["seq"], last["hash"]) if last else (0, GENESIS)
            at = int(time.time())
            for d in clean:
                seq += 1
                row = {"seq": seq, "at": at, "actor": actor, **d, "prev": prev}
                row["hash"] = row_hash(row)
                row["sig"] = sign(self.key, row["hash"])
                c.execute("INSERT INTO kb_decisions (seq, at, actor, key, action, value, draft, note, prev, hash, sig) "
                          "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                          (seq, at, actor, row["key"], row["action"],
                           json.dumps(row["value"], ensure_ascii=False) if row["value"] is not None else None,
                           json.dumps(row["draft"], ensure_ascii=False) if row["draft"] is not None else None,
                           row["note"], prev, row["hash"], row["sig"]))
                prev = row["hash"]
                out.append(row)
            self.store.audit(c, actor, f"kb_decisions:{len(out)}")
        return out

    def all(self):
        with self.store.db() as c:
            return [self._row(r) for r in c.execute("SELECT * FROM kb_decisions ORDER BY seq")]

    def history(self, key):
        with self.store.db() as c:
            return [self._row(r) for r in c.execute("SELECT * FROM kb_decisions WHERE key = ? ORDER BY seq", (key,))]

    def verify(self):
        return verify_chain(self.all(), self.key)

    def export(self, kb_version=""):
        rows = self.all()
        ok, msg = verify_chain(rows, self.key)
        if not ok:
            raise Invalid("the decision log failed verification: " + msg)
        return {
            "schema_version": "kb_decisions.v1",
            "exported_at": int(time.time()),
            "kb_version": kb_version,
            "note": "Clinician decisions over the draft knowledge base. Written by the clinic server; do not edit by hand "
                    "(each row's hash covers its content and the row before it).",
            "head": rows[-1]["hash"] if rows else GENESIS,
            "rows": rows,
        }


# ---------------------------------------------------------------------------------------------
# For the builds: read kb/approvals/decisions.json and lay the decisions over the draft data.

def load_export(path: Path):
    """({key: row} of the effective decisions, seq of the last row); ({}, 0) with no file.
    Stops the build when the chain is broken."""
    path = Path(path)
    if not path.exists():
        return {}, 0
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("rows", [])
    ok, msg = verify_chain(rows)
    if not ok:
        raise SystemExit(f"{path}: {msg}. Export it again from the clinic server.")
    if rows and data.get("head") != rows[-1]["hash"]:
        raise SystemExit(f"{path}: rows were removed from the end. Export it again from the clinic server.")
    return effective(rows), (rows[-1]["seq"] if rows else 0)


def stamp(row):
    """What the built data carries about a decision: who, when, which log row."""
    return {"by": row["actor"].split(":", 1)[-1], "at": row["at"], "seq": row["seq"]}
