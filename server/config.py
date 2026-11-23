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
    timezone: str = "Asia/Jerusalem"
    public_base: str = "http://127.0.0.1:8000"   # where the clinician's browser reaches the server (Google sign-in returns here)
    run_jobs: bool = True                        # the background loop: Google sync, WhatsApp queue, daily backup
    wa_token: str = ""                           # WhatsApp Cloud API: a system-user access token
    wa_phone_id: str = ""                        # WhatsApp Cloud API: the phone number id
    wa_verify_token: str = ""                    # webhook: the verify token you typed in the Meta app
    wa_app_secret: str = ""                      # webhook: the Meta app secret (checks X-Hub-Signature-256)
    google_client_id: str = ""                   # Google Calendar: OAuth client of type "Desktop app"
    google_client_secret: str = ""

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
        timezone=os.environ.get("TCM_TIMEZONE", "Asia/Jerusalem"),
        public_base=os.environ.get("TCM_PUBLIC_BASE", "http://127.0.0.1:8000"),
        run_jobs=os.environ.get("TCM_JOBS", "1") != "0",
        wa_token=os.environ.get("TCM_WA_TOKEN", ""),
        wa_phone_id=os.environ.get("TCM_WA_PHONE_ID", ""),
        wa_verify_token=os.environ.get("TCM_WA_VERIFY_TOKEN", ""),
        wa_app_secret=os.environ.get("TCM_WA_APP_SECRET", ""),
        google_client_id=os.environ.get("TCM_GOOGLE_CLIENT_ID", ""),
        google_client_secret=os.environ.get("TCM_GOOGLE_CLIENT_SECRET", ""),
    )
    for k, v in overrides.items():
        setattr(s, k, v)
    return s
