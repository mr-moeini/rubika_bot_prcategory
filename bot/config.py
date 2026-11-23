"""Settings, read from environment variables (see .env.example)."""
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    token: str = field(default_factory=lambda: os.getenv("RUBIKA_BOT_TOKEN", "").strip())
    # Comma separated chat_ids (e.g. g0AbC...). Empty = any chat the bot sits in.
    allowed_chats: set = field(default_factory=lambda: {
        c.strip() for c in os.getenv("ALLOWED_CHAT_IDS", "").split(",") if c.strip()})
    file_pattern: re.Pattern = field(default_factory=lambda: re.compile(
        os.getenv("FILE_PATTERN", r"^Behsa_Report.*\.xlsx?$"), re.IGNORECASE))
    drop_columns: tuple = ("شماره موبایل",)
    poll_interval: float = float(os.getenv("POLL_INTERVAL", "3"))
    process_backlog: bool = _bool("PROCESS_BACKLOG", False)
    send_xlsx: bool = _bool("SEND_XLSX", True)
    state_file: Path = Path(os.getenv("STATE_FILE", str(ROOT / "data" / "state.json")))
    font_regular: Path = ROOT / "fonts" / "Vazirmatn-Regular.ttf"
    font_bold: Path = ROOT / "fonts" / "Vazirmatn-Bold.ttf"
    min_confidence: float = float(os.getenv("MIN_CONFIDENCE", "0.30"))
