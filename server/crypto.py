"""AES-256-GCM encryption for everything clinical or identifying.

Two keys, kept apart: "data" encrypts the clinical documents and "identity" encrypts the optional
name and phone the clinician attaches to a record. A copy of the database without the identity key
holds no way back to the person. Each key is 32 random bytes, base64 in a file with mode 0600, or in
the environment (TCM_DATA_KEY / TCM_IDENTITY_KEY). The key id stored with every blob is a hash prefix,
so a rotated-out key can stay in the folder as <name>.<id>.old.key and old rows still open.

The associated data binds each blob to its record, kind and version: a blob copied to another row
fails to decrypt instead of showing the wrong patient's data.
"""
import base64
import hashlib
import json
import os
import secrets
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

KEY_NAMES = ("data", "identity")


def key_id(key: bytes) -> str:
    return hashlib.sha256(key).hexdigest()[:12]


def create_keys(key_dir: Path):
    """Write any missing key file. Never overwrites an existing key."""
    key_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(key_dir, 0o700)
    made = []
    for name in KEY_NAMES:
        path = key_dir / f"{name}.key"
        if path.exists():
            continue
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(base64.b64encode(secrets.token_bytes(32)).decode("ascii") + "\n")
        made.append(path)
    return made


def _decode(text: str) -> bytes:
    key = base64.b64decode(text.strip())
    if len(key) != 32:
        raise ValueError("an encryption key must be 32 bytes (base64)")
    return key


class Box:
    """Encrypts with the current key of each name; decrypts with any key it has seen."""

    def __init__(self, keys):
        # keys: {name: [current_key, older_key, ...]}
        self.current = {}
        self.by_id = {}
        for name, ks in keys.items():
            if not ks:
                raise ValueError(f"no {name} key")
            self.current[name] = (key_id(ks[0]), AESGCM(ks[0]))
            for k in ks:
                self.by_id[(name, key_id(k))] = AESGCM(k)

    @classmethod
    def load(cls, key_dir: Path):
        keys = {}
        for name in KEY_NAMES:
            env = os.environ.get(f"TCM_{name.upper()}_KEY")
            current = _decode(env) if env else None
            path = key_dir / f"{name}.key"
            if current is None:
                if not path.exists():
                    raise FileNotFoundError(f"missing {path}: run `python -m server.manage init` first")
                current = _decode(path.read_text())
            old = [_decode(p.read_text()) for p in sorted(key_dir.glob(f"{name}.*.old.key"))]
            keys[name] = [current] + old
        return cls(keys)

    def seal(self, name: str, obj, aad: str):
        kid, aes = self.current[name]
        nonce = secrets.token_bytes(12)
        data = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return kid, nonce, aes.encrypt(nonce, data, aad.encode("utf-8"))

    def open(self, name: str, kid: str, nonce: bytes, blob: bytes, aad: str):
        aes = self.by_id.get((name, kid))
        if aes is None:
            raise KeyError(f"{name} key {kid} is not available")
        return json.loads(aes.decrypt(nonce, blob, aad.encode("utf-8")).decode("utf-8"))
