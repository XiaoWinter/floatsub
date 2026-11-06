import json
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
STATE_PATH = DATA / "state.json"

load_dotenv(ROOT / ".env")


def _float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


class Settings:
    provider = os.getenv("FLOATSUB_PROVIDER", "gemini").strip().lower() or "gemini"
    gemini_api_key = os.getenv("GEMINI_API_KEY", "").strip()
    gemini_live_model = (
        os.getenv("GEMINI_LIVE_MODEL", "gemini-3.5-live-translate-preview").strip()
        or "gemini-3.5-live-translate-preview"
    )
    qwen_api_key = os.getenv("DASHSCOPE_API_KEY", "").strip() or os.getenv("QWEN_API_KEY", "").strip()
    qwen_base_url = os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/api/v1").strip().rstrip("/")
    qwen_live_model = (
        os.getenv("QWEN_LIVE_MODEL", "qwen3.8-livetranslate-flash-realtime").strip()
        or "qwen3.8-livetranslate-flash-realtime"
    )
    chunk_seconds = max(3.0, _float("FLOATSUB_CHUNK_SECONDS", 5.0))


settings = Settings()


def load_state() -> dict:
    if not STATE_PATH.is_file():
        return {}
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_state(state: dict) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(state, ensure_ascii=False, indent=2)
    temporary = STATE_PATH.with_suffix(".json.tmp")
    temporary.write_text(payload, encoding="utf-8")
    temporary.replace(STATE_PATH)
