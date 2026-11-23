"""Clinician passwords (scrypt) and a small lockout after repeated failures."""
import base64
import hashlib
import hmac
import secrets
import time

N, R, P = 2 ** 14, 8, 1


def hash_password(password: str) -> str:
    if len(password) < 10:
        raise ValueError("a password needs at least 10 characters")
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=N, r=R, p=P, dklen=32)
    return f"scrypt${N}${R}${P}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def check_password(password: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, dk = stored.split("$")
        got = hashlib.scrypt(password.encode("utf-8"), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p), dklen=32)
        return hmac.compare_digest(got, base64.b64decode(dk))
    except (ValueError, TypeError):
        return False


class Lockout:
    """Five failed sign-ins for a username lock it for five minutes."""

    def __init__(self, limit=5, seconds=300):
        self.limit, self.seconds = limit, seconds
        self.fails = {}

    def locked(self, username):
        n, since = self.fails.get(username, (0, 0))
        if n >= self.limit and time.time() - since < self.seconds:
            return True
        if n >= self.limit:
            self.fails.pop(username, None)
        return False

    def fail(self, username):
        n, _ = self.fails.get(username, (0, 0))
        self.fails[username] = (n + 1, time.time())

    def ok(self, username):
        self.fails.pop(username, None)
