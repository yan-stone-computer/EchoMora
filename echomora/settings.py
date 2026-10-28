from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


@dataclass(slots=True)
class Settings:
    db_path: Path
    host: str = "127.0.0.1"
    port: int = 8765
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    chat_model: str = "deepseek-chat"
    extract_model: str = "deepseek-chat"
    short_term_turns: int = 24
    recall_top_n: int = 8
    candidate_limit: int = 32
    token_budget: int = 1800
    half_life_days: float = 30.0
    random_forget_rate: float = 0.12

    @property
    def llm_enabled(self) -> bool:
        return bool(self.deepseek_api_key.strip())

    @classmethod
    def load(cls, cwd: Path | None = None) -> "Settings":
        root = (cwd or Path.cwd()).resolve()
        _load_dotenv(root / ".env")
        db_value = os.getenv("ECHOMORA_DB", "data/echomora.db")
        db_path = Path(db_value)
        if not db_path.is_absolute():
            db_path = root / db_path
        return cls(
            db_path=db_path,
            host=os.getenv("ECHOMORA_HOST", "127.0.0.1"),
            port=_int("ECHOMORA_PORT", 8765),
            deepseek_api_key=os.getenv("DEEPSEEK_API_KEY", "").strip(),
            deepseek_base_url=os.getenv(
                "DEEPSEEK_BASE_URL", "https://api.deepseek.com"
            ).rstrip("/"),
            chat_model=os.getenv("DEEPSEEK_CHAT_MODEL", "deepseek-chat"),
            extract_model=os.getenv("DEEPSEEK_EXTRACT_MODEL", "deepseek-chat"),
            short_term_turns=_int("ECHOMORA_SHORT_TERM_TURNS", 24),
            recall_top_n=_int("ECHOMORA_RECALL_TOP_N", 8),
            candidate_limit=_int("ECHOMORA_CANDIDATE_LIMIT", 32),
            token_budget=_int("ECHOMORA_TOKEN_BUDGET", 1800),
            half_life_days=_float("ECHOMORA_HALF_LIFE_DAYS", 30.0),
            random_forget_rate=_float("ECHOMORA_RANDOM_FORGET_RATE", 0.12),
        )

