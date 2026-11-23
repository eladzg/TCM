"""Where the server keeps its database and keys. Every setting can come from the environment."""
import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Settings:
    data_dir: Path
    key_dir: Path
    app_dir: Path
    token_days: int = 7          # how long a patient intake link stays open
    session_hours: int = 12      # how long a clinician stays signed in
    force_secure_cookie: bool = False

    @property
    def db_path(self):
        return self.data_dir / "records.db"


def load_settings(**overrides):
    data_dir = Path(os.environ.get("TCM_DATA_DIR", ROOT / "data" / "server"))
    s = Settings(
        data_dir=data_dir,
        key_dir=Path(os.environ.get("TCM_KEY_DIR", data_dir / "keys")),
        app_dir=Path(os.environ.get("TCM_APP_DIR", ROOT / "app" / "interview")),
        token_days=int(os.environ.get("TCM_TOKEN_DAYS", 7)),
        session_hours=int(os.environ.get("TCM_SESSION_HOURS", 12)),
        force_secure_cookie=os.environ.get("TCM_SECURE_COOKIE") == "1",
    )
    for k, v in overrides.items():
        setattr(s, k, v)
    return s
