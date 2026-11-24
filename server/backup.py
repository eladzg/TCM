"""Encrypted backups of the clinic database, and a restore check.

A backup is SQLite's own online copy of records.db, gzipped and sealed with AES-256-GCM under a third
key, keys/backup.key. Inside, the clinical and identity blobs stay sealed under their own keys, so to
read a backup you need backup.key and data.key (and identity.key for names). Keep a copy of the key
folder somewhere other than the backups, or a lost disk takes both.

The server makes one a day while it runs (and at start-up if the last one is older than a day) and
keeps the newest `keep` (14). `python -m server.manage backup` makes one now; `restore-check <file>`
opens a backup in a temporary folder, runs SQLite's integrity check and opens one document with the
current keys, without touching the live database.
"""
import base64
import gzip
import hashlib
import os
import secrets
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC = b"TCMBAK1"


def load_key(key_dir, create=True):
    env = os.environ.get("TCM_BACKUP_KEY")
    if env:
        return base64.b64decode(env.strip())
    path = Path(key_dir) / "backup.key"
    if not path.exists():
        if not create:
            raise FileNotFoundError(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(base64.b64encode(secrets.token_bytes(32)).decode("ascii") + "\n")
    return base64.b64decode(path.read_text().strip())


def backup_dir(settings):
    return Path(os.environ.get("TCM_BACKUP_DIR", settings.data_dir / "backups"))


def make(settings, keep=14):
    key = load_key(settings.key_dir)
    out_dir = backup_dir(settings)
    out_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(out_dir, 0o700)
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "copy.db"
        src = sqlite3.connect(settings.db_path)
        dst = sqlite3.connect(copy)
        with dst:
            src.backup(dst)
        src.close()
        dst.close()
        raw = gzip.compress(copy.read_bytes(), 6)
    nonce = secrets.token_bytes(12)
    kid = hashlib.sha256(key).hexdigest()[:12].encode()
    sealed = MAGIC + kid + nonce + AESGCM(key).encrypt(nonce, raw, MAGIC + kid)
    name = "records-" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".db.gz.enc"
    path = out_dir / name
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(sealed)
    old = sorted(out_dir.glob("records-*.db.gz.enc"))
    for p in old[:-keep] if keep else []:
        p.unlink()
    return path


def latest(settings):
    files = sorted(backup_dir(settings).glob("records-*.db.gz.enc"))
    return files[-1] if files else None


def age_hours(settings):
    p = latest(settings)
    if not p:
        return None
    return (datetime.now().timestamp() - p.stat().st_mtime) / 3600


def open_backup(settings, path, dest):
    key = load_key(settings.key_dir, create=False)
    data = Path(path).read_bytes()
    if not data.startswith(MAGIC):
        raise ValueError("not a TCM backup")
    kid, nonce, ct = data[len(MAGIC):len(MAGIC) + 12], data[len(MAGIC) + 12:len(MAGIC) + 24], data[len(MAGIC) + 24:]
    raw = AESGCM(key).decrypt(nonce, ct, MAGIC + kid)
    Path(dest).write_bytes(gzip.decompress(raw))


def check(settings, path):
    """Open a backup in a temporary folder and prove it can be read. Returns a summary dict."""
    from .crypto import Box
    from .store import Store
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "records.db"
        open_backup(settings, path, db)
        c = sqlite3.connect(db)
        ok = c.execute("PRAGMA integrity_check").fetchone()[0]
        counts = {t: c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("records", "documents", "pm_appointments", "pm_notes")
                  if c.execute("SELECT 1 FROM sqlite_master WHERE name = ?", (t,)).fetchone()}
        c.close()
        store = Store(db, Box.load(settings.key_dir))
        opened = 0
        docs = store.all_docs()
        if docs:
            opened = 1     # all_docs() decrypts every document; an exception means a key is missing
        return {"file": str(path), "integrity": ok, "counts": counts, "documents_opened": len(docs) if opened else 0}
